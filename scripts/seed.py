from services.api.audit import append_event
from services.api.config import settings
from services.api.database import Approval, PolicyRecord, SessionLocal, User
from services.api.operations import ingest, process_run, request_run
from .fixtures import make_fixtures
from packages.reconciliation.contracts import digest
import copy

DEMO_USERS = [
    ("demo-analyst", "Alex Morgan", "analyst", ["*"]),
    ("demo-reviewer", "Sam Chen", "reviewer", ["*"]),
    ("demo-approver", "Jordan Lee", "finance_approver", ["*"]),
    ("demo-admin", "Taylor Reed", "integration_admin", ["*"]),
    ("demo-viewer", "Casey Patel", "viewer", ["US100"]),
    ("demo-auditor", "Robin Ellis", "auditor", ["*"]),
]


def seed():
    if settings.app_mode != "demo":
        raise RuntimeError("Synthetic seeding is available only in demo mode")
    with SessionLocal.begin() as db:
        for user_id, name, role, entities in DEMO_USERS:
            if not db.get(User, user_id):
                db.add(User(id=user_id, name=name, role=role, entities=entities))
        policy, bundles = make_fixtures()
        if not db.get(PolicyRecord, policy["id"]):
            db.add(PolicyRecord(id=policy["id"], document=policy, author="demo-analyst"))
            db.flush()
            db.add(Approval(id="demo-approval-v1", policy_id=policy["id"], actor="demo-approver"))
            append_event(db, "demo-approver", "policy.approved", policy["id"], {"synthetic": True})
        user = db.get(User, "demo-analyst")
        batches = {side: ingest(db, user, raw, manifest) for side, (raw, manifest) in bundles.items()}
        baseline_raw = bundles["GL"][0]
        baseline_manifest = copy.deepcopy(bundles["FCCS"][1])
        baseline_manifest.update(dataset_id="Synthetic comparison baseline", sha256=digest(baseline_raw),
                                 byte_count=len(baseline_raw), totals_by_currency=bundles["GL"][1]["totals_by_currency"])
        baseline = ingest(db, user, baseline_raw, baseline_manifest)
        baseline_run = request_run(db, user, batches["GL"].id, baseline.id, policy["id"])
        baseline_id = baseline_run.id
        run = request_run(db, user, batches["GL"].id, batches["FCCS"].id, policy["id"])
        run_id = run.id
    process_run(baseline_id)
    process_run(run_id)
    print(f"Synthetic validation available {run_id[:12]}")


if __name__ == "__main__":
    seed()
