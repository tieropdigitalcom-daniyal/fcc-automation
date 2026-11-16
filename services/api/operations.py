from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from packages.reconciliation.contracts import Manifest, Policy, Row, canonical, digest
from packages.reconciliation.engine import RULE_VERSION, coverage, validate
from packages.source_connectors.csv_import import parse_csv
from .audit import append_event
from .auth import scoped
from .database import Approval, Batch, ExceptionCase, Notification, PolicyRecord, Run, SessionLocal, utcnow
from .storage import EvidenceStore


def ingest(db, user, raw, metadata):
    manifest = Manifest.model_validate(metadata)
    rows = parse_csv(raw)
    entities = sorted({row.pov.entity for row in rows} | {pov.entity for pov in manifest.expected_povs})
    scoped(user, entities)
    policy = db.get(PolicyRecord, manifest.policy_id)
    if policy is None:
        raise HTTPException(422, "Import the referenced policy first")
    batch_id = digest({"manifest": manifest.model_dump(), "actual_sha256": digest(raw)})
    existing = db.get(Batch, batch_id)
    if existing:
        return existing
    store = EvidenceStore()
    actual_hash = store.put(raw)
    store.put(canonical(manifest.model_dump()).encode())
    batch = Batch(id=batch_id, name=manifest.dataset_id, side=manifest.side, sha256=actual_hash,
                  manifest=manifest.model_dump(), entities=entities,
                  rows=[row.model_dump() for row in rows], imported_by=user.id)
    db.add(batch)
    append_event(db, user.id, "batch.imported", batch_id, {"sha256": actual_hash, "records": len(rows)})
    db.flush()
    return batch


def batch_tuple(batch):
    return (batch.id, Manifest.model_validate(batch.manifest), [Row.model_validate(row) for row in batch.rows],
            EvidenceStore().get(batch.sha256))


def request_run(db, user, gl_id, fccs_id, policy_id, prior_id=None, occurrence=None):
    gl, fccs = db.get(Batch, gl_id), db.get(Batch, fccs_id)
    policy = db.get(PolicyRecord, policy_id)
    if not gl or not fccs or not policy or gl.side != "GL" or fccs.side != "FCCS":
        raise HTTPException(422, "Choose one GL batch, one FCCS batch and an existing policy")
    entities = sorted(set(gl.entities + fccs.entities))
    scoped(user, entities)
    if prior_id:
        prior = db.get(Batch, prior_id)
        if not prior or prior.side != "GL":
            raise HTTPException(422, "Prior snapshot must be an existing GL batch")
        scoped(user, prior.entities)
    approval = db.scalar(select(Approval).where(Approval.policy_id == policy_id))
    identity = {"gl": gl_id, "fccs": fccs_id, "policy": policy.document,
                "approval": approval.id if approval else None, "prior": prior_id,
                "rule_version": RULE_VERSION, "occurrence": occurrence}
    run_id = digest(identity)
    existing = db.get(Run, run_id)
    if existing:
        return existing
    run = Run(id=run_id, gl_id=gl_id, fccs_id=fccs_id, policy_id=policy_id, prior_id=prior_id,
              entities=entities, created_by=user.id)
    db.add(run)
    append_event(db, user.id, "validation.requested", run_id, {"identity_sha256": run_id})
    db.flush()
    return run


def process_run(run_id):
    with SessionLocal.begin() as db:
        # A no-op update obtains a write lock on SQLite too. A terminated task rolls
        # back its entire result transaction and can be safely redelivered.
        from sqlalchemy import update
        claimed = db.execute(update(Run).where(Run.id == run_id, Run.state == "QUEUED")
                             .values(attempts=Run.attempts + 1))
        if not claimed.rowcount:
            return
        run = db.get(Run, run_id)
        policy = Policy.model_validate(db.get(PolicyRecord, run.policy_id).document)
        approved = db.scalar(select(Approval).where(Approval.policy_id == policy.id)) is not None
        try:
            gl = batch_tuple(db.get(Batch, run.gl_id))
            fccs = batch_tuple(db.get(Batch, run.fccs_id))
            prior = batch_tuple(db.get(Batch, run.prior_id)) if run.prior_id else None
            if prior:
                prior_gates = coverage(*prior[:3], policy, prior[3], approved, datetime.now(timezone.utc))
                if any(check["status"] != "PASS" for check in prior_gates):
                    from packages.reconciliation.engine import finish
                    output = finish(prior_gates, policy)
                else:
                    output = validate(gl, fccs, policy, approved, prior=prior)
            else:
                output = validate(gl, fccs, policy, approved)
        except (ValueError, FileNotFoundError) as error:
            from packages.reconciliation.engine import finish, result
            output = finish([result("C01 Evidence integrity", "BLOCKED", "Stored evidence failed integrity verification")], policy)
            run.error = type(error).__name__
        run.result, run.state, run.completed = output, output["status"], utcnow()
        for check in output["checks"]:
            if check["status"] in {"FAIL", "BLOCKED"}:
                case_id = digest({"run": run.id, "check": check["fingerprint"]})
                if db.get(ExceptionCase, case_id) is None:
                    db.add(ExceptionCase(id=case_id, run_id=run.id, check=check))
        db.add(Notification(id=digest({"run": run.id, "event": "completed"}), run_id=run.id))
        append_event(db, "worker", "validation.completed", run.id,
                     {"status": run.state, "result_sha256": output["result_sha256"]})
