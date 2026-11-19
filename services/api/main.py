import json
import logging
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from packages.oracle_connector.rest import MockConnector, OracleClient, OracleError
from packages.reconciliation.contracts import Manifest, Policy, canonical, digest
from packages.source_connectors.csv_import import MAX_BYTES, unpack
from .audit import append_event, verify_chain
from .auth import ROLES, can_access, check_origin, current_user, issue_session, oidc_subject, require, scoped, session_secret
from .config import settings
from .database import Approval, AuditEvent, Batch, ExceptionCase, Notification, PolicyRecord, Run, Schedule, SessionLocal, User, get_db, utcnow
from .operations import ingest, process_run, request_run
from .reports import bundle_report, csv_report, pdf_report, report_document
from .storage import EvidenceStore

logger = logging.getLogger("fccs")


@asynccontextmanager
async def lifespan(app):
    settings.check()
    yield


app = FastAPI(title="FCCS Validation & Audit Agent", version="0.1.0", lifespan=lifespan,
              docs_url="/docs" if settings.app_mode == "demo" else None,
              openapi_url="/openapi.json" if settings.app_mode == "demo" else None)

# Allow the frontend (on a different domain in cloud deployments) to call the API
_cors_origins = [settings.public_origin]
if settings.app_mode == "demo":
    _cors_origins += ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])

app.add_middleware(SessionMiddleware, secret_key=session_secret(), session_cookie="fccs_oidc_state",
                   https_only=settings.app_mode == "production", same_site="lax", max_age=600)

oauth = OAuth()
if settings.oidc_issuer:
    oauth.register("enterprise", client_id=settings.oidc_client_id, client_secret=settings.oidc_client_secret,
                   server_metadata_url=settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"})


@app.middleware("http")
async def request_controls(request, call_next):
    request_id = secrets.token_hex(12)
    started = time.monotonic()
    if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > MAX_BYTES + 100000:
        return JSONResponse({"detail": "Request exceeds upload limit"}, status_code=413)
    response = await call_next(request)
    actor = getattr(request.state, "actor", None)
    if actor and request.url.path.startswith("/api/"):
        with SessionLocal.begin() as audit_db:
            append_event(audit_db, actor, "api.accessed", request.url.path,
                         {"method": request.method, "status": response.status_code, "request_id": request_id})
    response.headers.update({"X-Request-ID": request_id, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
    logger.info(json.dumps({"event": "http", "request_id": request_id, "method": request.method,
                            "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000)}))
    return response


@app.exception_handler(ValueError)
async def invalid_input(request, error):
    return JSONResponse({"detail": "Input or evidence validation failed. Check the schema, amounts and manifest."}, status_code=422)


@app.exception_handler(zipfile.BadZipFile)
async def invalid_archive(request, error):
    return JSONResponse({"detail": "Invalid or corrupted ZIP package"}, status_code=422)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Body):
    user_id: str


class RunRequest(Body):
    gl_id: str
    fccs_id: str
    policy_id: str
    prior_id: str | None = None


class CaseUpdate(Body):
    state: str
    owner: str | None = None
    comment: str = Field(min_length=3, max_length=2000)
    version: int = Field(ge=0)
    evidence_run_id: str | None = None


class ScheduleRequest(RunRequest):
    name: str = Field(min_length=1, max_length=160)
    interval_minutes: int = Field(ge=5, le=525600)


class UserRequest(Body):
    subject: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=160)
    role: str
    entities: list[str] = Field(min_length=1)


def user_json(user):
    return {"id": user.id, "name": user.name, "role": user.role, "entities": user.entities, "active": user.active}


def run_json(run, full=False):
    return {"id": run.id, "state": run.state, "entities": run.entities, "created": run.created,
            "completed": run.completed, "created_by": run.created_by, "policy_id": run.policy_id,
            "gl_id": run.gl_id, "fccs_id": run.fccs_id, "prior_id": run.prior_id,
            "counts": (run.result or {}).get("counts", {}), "attempts": run.attempts,
            **({"result": run.result, "error": run.error} if full else {})}


def batch_json(batch):
    return {"id": batch.id, "name": batch.name, "side": batch.side, "sha256": batch.sha256,
            "created": batch.created, "entities": batch.entities, "manifest": batch.manifest,
            "row_count": len(batch.rows)}


def get_run(db, user, run_id):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    scoped(user, run.entities)
    return run


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.app_mode}


@app.get("/ready")
def readiness(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    if settings.queue_mode == "celery":
        from redis import Redis
        Redis.from_url(settings.redis_url, socket_timeout=3).ping()
    return {"status": "ready"}


@app.get("/api/config")
def config():
    return {"mode": settings.app_mode, "identity": "Demo profiles" if settings.app_mode == "demo" else "Enterprise SSO"}


@app.get("/api/demo/users")
def demo_users(db=Depends(get_db)):
    if settings.app_mode != "demo":
        raise HTTPException(404)
    return [user_json(user) for user in db.scalars(select(User).where(User.id.like("demo-%")))]


@app.post("/api/auth/demo")
def demo_login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    if settings.app_mode != "demo":
        raise HTTPException(404)
    check_origin(request)
    user = db.get(User, body.user_id)
    if not user or not user.id.startswith("demo-") or not user.active:
        raise HTTPException(401, "Unknown synthetic profile")
    session = issue_session(db, user, response)
    append_event(db, user.id, "session.started", user.id, {"mode": "demo"})
    db.commit()
    return {"user": user_json(user), "csrf": session.csrf}


@app.get("/api/auth/login")
async def sso_login(request: Request):
    if not settings.oidc_issuer:
        raise HTTPException(503, "Enterprise SSO has not been configured")
    return await oauth.enterprise.authorize_redirect(request, settings.public_origin + "/api/auth/callback")


@app.get("/api/auth/callback")
async def sso_callback(request: Request, db=Depends(get_db)):
    if not settings.oidc_issuer:
        raise HTTPException(503, "Enterprise SSO has not been configured")
    try:
        token = await oauth.enterprise.authorize_access_token(request)
        # Authlib verifies issuer, audience, signature, nonce and expiry from discovery.
        subject = token["userinfo"]["sub"]
    except Exception:
        raise HTTPException(401, "Enterprise identity validation failed") from None
    user = db.get(User, oidc_subject(subject))
    if not user or not user.active:
        raise HTTPException(403, "Identity requires explicit provisioning")
    response = RedirectResponse(settings.public_origin, status_code=303)
    issue_session(db, user, response)
    append_event(db, user.id, "session.started", user.id, {"mode": "oidc"})
    db.commit()
    return response


@app.get("/api/session")
def session(request: Request, user=Depends(current_user)):
    return {"user": user_json(user), "csrf": request.state.session.csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(request.state.session)
    append_event(db, user.id, "session.ended", user.id)
    db.commit()
    response.delete_cookie("fccs_session")
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    runs = [run for run in db.scalars(select(Run).order_by(Run.created.desc())) if can_access(user, run.entities)]
    ids = [run.id for run in runs]
    cases = db.scalars(select(ExceptionCase).where(ExceptionCase.run_id.in_(ids))).all() if ids else []
    latest = runs[0] if runs else None
    return {"latest": run_json(latest, True) if latest else None, "runs": [run_json(run) for run in runs[:8]],
            "run_count": len(runs), "open_exceptions": sum(case.state not in {"RESOLVED", "ACCEPTED_RISK"} for case in cases),
            "entities": sorted({entity for run in runs for entity in run.entities}),
            "storage": settings.storage_backend, "database": "PostgreSQL" if settings.database_url.startswith("postgresql") else "SQLite local demo",
            "worker": settings.queue_mode, "oracle": "LIVE UNVERIFIED" if settings.oracle_enabled else "MOCK ONLY"}


@app.get("/api/batches")
def batches(user=Depends(current_user), db=Depends(get_db)):
    return [batch_json(batch) for batch in db.scalars(select(Batch).order_by(Batch.created.desc())) if can_access(user, batch.entities)]


@app.post("/api/batches")
async def import_batch(file: UploadFile = File(...), manifest: str | None = Form(None), user=Depends(current_user), db=Depends(get_db)):
    require(user, "analyst", "integration_admin")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds 20 MB")
    if (file.filename or "").lower().endswith(".zip"):
        raw, metadata = unpack(data)
    else:
        if not manifest:
            raise HTTPException(422, "A source manifest is required with a CSV upload")
        raw, metadata = data, json.loads(manifest)
    try:
        batch = ingest(db, user, raw, metadata)
        db.commit()
    except IntegrityError:
        db.rollback()
        identifier = digest({"manifest": Manifest.model_validate(metadata).model_dump(), "actual_sha256": digest(raw)})
        batch = db.get(Batch, identifier)
        if not batch:
            raise HTTPException(409, "Import conflicted. Retry the identical package") from None
        scoped(user, batch.entities)
    return batch_json(batch)


@app.get("/api/batches/{batch_id}/evidence")
def evidence(batch_id: str, user=Depends(current_user), db=Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404)
    scoped(user, batch.entities)
    data = EvidenceStore().get(batch.sha256)
    append_event(db, user.id, "evidence.downloaded", batch.id, {"sha256": batch.sha256})
    db.commit()
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="source-{batch.id[:12]}.csv"'})


@app.get("/api/batches/{batch_id}/rows")
def source_rows(batch_id: str, offset: int = 0, limit: int = 50, user=Depends(current_user), db=Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404)
    scoped(user, batch.entities)
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid page bounds")
    return {"items": batch.rows[offset:offset + limit], "total": len(batch.rows), "sha256": batch.sha256}


@app.get("/api/runs")
def runs(user=Depends(current_user), db=Depends(get_db)):
    return [run_json(run) for run in db.scalars(select(Run).order_by(Run.created.desc())) if can_access(user, run.entities)]


@app.post("/api/runs")
def create_run(body: RunRequest, user=Depends(current_user), db=Depends(get_db)):
    require(user, "analyst", "reviewer", "finance_approver", "integration_admin")
    try:
        run = request_run(db, user, **body.model_dump())
        db.commit()
    except IntegrityError:
        db.rollback()
        run = request_run(db, user, **body.model_dump())
        db.commit()
    if settings.queue_mode == "inline":
        process_run(run.id)
    else:
        from .worker import execute_run
        try:
            execute_run.delay(run.id)
        except Exception:
            logger.warning("Queue unavailable. Durable run awaits periodic dispatcher")
    db.expire_all()
    return run_json(db.get(Run, run.id), True)


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, user=Depends(current_user), db=Depends(get_db)):
    run = get_run(db, user, run_id)
    append_event(db, user.id, "run.viewed", run_id)
    db.commit()
    return run_json(run, True)


@app.get("/api/runs/{run_id}/report/{format_name}")
def report(run_id: str, format_name: str, user=Depends(current_user), db=Depends(get_db)):
    run = get_run(db, user, run_id)
    if not run.result:
        raise HTTPException(409, "Run has not completed")
    document = report_document(db, run)
    formats = {"json": (lambda value: json.dumps(value, indent=2).encode(), "application/json"),
               "csv": (csv_report, "text/csv"), "pdf": (pdf_report, "application/pdf"),
               "zip": (bundle_report, "application/zip")}
    if format_name not in formats:
        raise HTTPException(404)
    render, mime = formats[format_name]
    data = render(document)
    report_hash = EvidenceStore().put(data)
    append_event(db, user.id, "report.exported", run.id, {"format": format_name, "sha256": report_hash})
    db.commit()
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="audit-{run.id[:12]}.{format_name}"'})


@app.get("/api/exceptions")
def exceptions(run_id: str | None = None, user=Depends(current_user), db=Depends(get_db)):
    permitted = [run.id for run in db.scalars(select(Run)) if can_access(user, run.entities)]
    query = select(ExceptionCase).where(ExceptionCase.run_id.in_(permitted))
    if run_id:
        query = query.where(ExceptionCase.run_id == run_id)
    return [{"id": case.id, "run_id": case.run_id, "check": case.check, "state": case.state,
             "owner": case.owner, "version": case.version} for case in db.scalars(query)]


@app.get("/api/exceptions/{case_id}/history")
def case_history(case_id: str, user=Depends(current_user), db=Depends(get_db)):
    case = db.get(ExceptionCase, case_id)
    if not case:
        raise HTTPException(404)
    get_run(db, user, case.run_id)
    return [{"actor": event.actor, "action": event.action, "created": event.created, "payload": event.payload}
            for event in db.scalars(select(AuditEvent).where(AuditEvent.target == case_id).order_by(AuditEvent.sequence))]


@app.patch("/api/exceptions/{case_id}")
def update_case(case_id: str, body: CaseUpdate, user=Depends(current_user), db=Depends(get_db)):
    require(user, "analyst", "reviewer", "finance_approver")
    case = db.get(ExceptionCase, case_id)
    if not case:
        raise HTTPException(404)
    run = get_run(db, user, case.run_id)
    transitions = {"NEW": {"ASSIGNED"}, "ASSIGNED": {"IN_REVIEW"}, "IN_REVIEW": {"RESOLVED", "ACCEPTED_RISK", "ASSIGNED"},
                   "RESOLVED": {"IN_REVIEW"}, "ACCEPTED_RISK": {"IN_REVIEW"}}
    if body.state != case.state and body.state not in transitions.get(case.state, set()):
        raise HTTPException(409, "Invalid exception transition")
    owner = body.owner or case.owner
    assigned = db.get(User, owner) if owner else None
    if not assigned or not assigned.active or not can_access(assigned, run.entities) or assigned.role not in {"analyst", "reviewer", "finance_approver"}:
        raise HTTPException(422, "Assign an active reviewer or analyst with access to the full scope")
    if body.state in {"RESOLVED", "ACCEPTED_RISK"}:
        require(user, "finance_approver")
        if user.id in {owner, run.created_by}:
            raise HTTPException(403, "An independent finance approver must sign the disposition")
        if body.state == "RESOLVED":
            if not body.evidence_run_id:
                raise HTTPException(422, "Resolution requires a passing replacement run")
            proof = get_run(db, user, body.evidence_run_id)
            if proof.state != "PASS" or proof.id == run.id or set(proof.entities) != set(run.entities):
                raise HTTPException(422, "Resolution requires a passing replacement run covering the same entities")
            original_scope = db.get(Batch, run.fccs_id).manifest["expected_povs"]
            replacement_scope = db.get(Batch, proof.fccs_id).manifest["expected_povs"]
            if {canonical(pov) for pov in original_scope} != {canonical(pov) for pov in replacement_scope}:
                raise HTTPException(422, "Replacement evidence must cover the same full POV universe")
    old_state = case.state
    changed = db.execute(update(ExceptionCase).where(ExceptionCase.id == case_id, ExceptionCase.version == body.version)
                         .values(state=body.state, owner=owner, version=ExceptionCase.version + 1))
    if not changed.rowcount:
        raise HTTPException(409, "Exception changed during review. Refresh and retry")
    append_event(db, user.id, "exception.reviewed", case.id, {"from": old_state, "to": body.state,
                 "owner": owner, "comment": body.comment, "evidence_run_id": body.evidence_run_id})
    db.commit()
    return {"id": case_id, "state": body.state, "version": body.version + 1}


@app.get("/api/policies")
def policies(user=Depends(current_user), db=Depends(get_db)):
    result = []
    for policy in db.scalars(select(PolicyRecord)):
        if can_access(user, policy.document["members"].get("entity", [])):
            approval = db.scalar(select(Approval).where(Approval.policy_id == policy.id))
            result.append({"id": policy.id, "document": policy.document, "author": policy.author,
                           "approved_by": approval.actor if approval else None, "sha256": digest(policy.document)})
    return result


@app.post("/api/policies")
def propose_policy(body: Policy, user=Depends(current_user), db=Depends(get_db)):
    require(user, "analyst", "integration_admin")
    scoped(user, body.members.get("entity", []))
    if db.get(PolicyRecord, body.id):
        raise HTTPException(409, "Use a new policy version ID")
    db.add(PolicyRecord(id=body.id, document=body.model_dump(), author=user.id))
    append_event(db, user.id, "policy.proposed", body.id, {"sha256": digest(body.model_dump())})
    db.commit()
    return {"id": body.id, "state": "PENDING_APPROVAL"}


@app.post("/api/policies/{policy_id}/approve")
def approve_policy(policy_id: str, user=Depends(current_user), db=Depends(get_db)):
    require(user, "finance_approver")
    policy = db.get(PolicyRecord, policy_id)
    if not policy:
        raise HTTPException(404)
    scoped(user, policy.document["members"]["entity"])
    if policy.author == user.id:
        raise HTTPException(403, "A policy author cannot approve their own version")
    if db.scalar(select(Approval).where(Approval.policy_id == policy_id)):
        raise HTTPException(409, "Policy is already approved")
    db.add(Approval(id=digest({"policy": policy_id, "actor": user.id}), policy_id=policy_id, actor=user.id))
    append_event(db, user.id, "policy.approved", policy_id, {"sha256": digest(policy.document)})
    db.commit()
    return {"state": "APPROVED"}


@app.get("/api/users")
def users(user=Depends(current_user), db=Depends(get_db)):
    return [user_json(item) for item in db.scalars(select(User)) if item.active and
            ("*" in user.entities or set(item.entities).issubset(user.entities))]


@app.post("/api/users")
def provision_user(body: UserRequest, user=Depends(current_user), db=Depends(get_db)):
    require(user, "integration_admin")
    if body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    scoped(user, body.entities)
    identifier = oidc_subject(body.subject)
    if db.get(User, identifier):
        raise HTTPException(409, "Identity already provisioned")
    db.add(User(id=identifier, name=body.name, role=body.role, entities=body.entities))
    append_event(db, user.id, "user.provisioned", identifier, {"role": body.role, "entities": body.entities})
    db.commit()
    return {"id": identifier}


@app.get("/api/connections")
def connections(user=Depends(current_user)):
    require(user, "integration_admin", "analyst", "reviewer", "finance_approver", "auditor")
    return {"mode": "LIVE UNVERIFIED" if settings.oracle_enabled else "MOCK ONLY",
            "application": settings.oracle_application or "FCCS_DEMO", "environment": settings.oracle_environment,
            "configured": bool(settings.oracle_base_url), "export_enabled": False,
            "origin": settings.oracle_base_url or "Synthetic offline fixture", "auth": "OAuth 2.0 user context",
            "capabilities": [{"name": "Application access", "state": "UNVERIFIED"},
                             {"name": "Export and download", "state": "CONTRACT TESTS"},
                             {"name": "Journal and IC report extraction", "state": "TENANT VERIFICATION REQUIRED"}]}


@app.post("/api/connections/test")
async def test_connection(user=Depends(current_user), db=Depends(get_db)):
    require(user, "integration_admin")
    if not settings.oracle_enabled:
        output = MockConnector().test_connection()
    else:
        if settings.oracle_environment != "test":
            raise HTTPException(403, "Only the approved non-production environment can be tested")
        import os
        client = OracleClient(settings.oracle_base_url, settings.oracle_application, lambda: os.getenv("ORACLE_ACCESS_TOKEN", ""))
        try:
            output = await client.test_connection()
        except (OracleError, ValueError):
            output = {"status": "BLOCKED", "message": "Oracle access or contract validation failed"}
        finally:
            await client.close()
    append_event(db, user.id, "connection.tested", "oracle", {"status": output["status"]})
    db.commit()
    return output


@app.get("/api/jobs")
def jobs(user=Depends(current_user), db=Depends(get_db)):
    return {"mode": settings.queue_mode, "runs": runs(user, db),
            "notifications": [{"run_id": item.run_id, "state": item.state, "attempts": item.attempts}
                              for item in db.scalars(select(Notification)) if can_access(user, db.get(Run, item.run_id).entities)],
            "alert_configured": bool(settings.notification_url)}


@app.get("/api/schedules")
def schedules(user=Depends(current_user), db=Depends(get_db)):
    return [{"id": item.id, "name": item.name, "interval_minutes": item.interval_minutes,
             "next_due": item.next_due, "enabled": item.enabled, "gl_id": item.gl_id, "fccs_id": item.fccs_id}
            for item in db.scalars(select(Schedule)) if can_access(user, db.get(Batch, item.gl_id).entities)
            and can_access(user, db.get(Batch, item.fccs_id).entities)]


@app.post("/api/schedules")
def add_schedule(body: ScheduleRequest, user=Depends(current_user), db=Depends(get_db)):
    require(user, "integration_admin")
    if settings.queue_mode != "celery":
        raise HTTPException(409, "Enable the Celery worker and beat services to activate durable schedules")
    run = request_run(db, user, body.gl_id, body.fccs_id, body.policy_id)
    identifier = secrets.token_hex(16)
    db.add(Schedule(id=identifier, name=body.name, gl_id=body.gl_id, fccs_id=body.fccs_id, policy_id=body.policy_id,
                    interval_minutes=body.interval_minutes, next_due=utcnow(), actor=user.id))
    append_event(db, user.id, "schedule.created", identifier, {"scope": run.entities})
    db.commit()
    return {"id": identifier}


@app.delete("/api/schedules/{schedule_id}")
def disable_schedule(schedule_id: str, user=Depends(current_user), db=Depends(get_db)):
    require(user, "integration_admin")
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404)
    scoped(user, db.get(Batch, schedule.gl_id).entities)
    scoped(user, db.get(Batch, schedule.fccs_id).entities)
    schedule.enabled = False
    append_event(db, user.id, "schedule.disabled", schedule_id)
    db.commit()
    return {"enabled": False}


@app.get("/api/audit")
def audit(user=Depends(current_user), db=Depends(get_db)):
    require(user, "auditor", "integration_admin", "finance_approver")
    if "*" not in user.entities:
        raise HTTPException(403, "Organization-wide audit requires full scope")
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(200)).all()
    return {"chain_valid": verify_chain(db), "events": [{"sequence": event.sequence, "actor": event.actor,
            "action": event.action, "target": event.target, "created": event.created, "hash": event.hash,
            "payload": event.payload} for event in events]}
