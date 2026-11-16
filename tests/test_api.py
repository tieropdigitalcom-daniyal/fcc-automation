import copy
import io
import json
import os
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# An isolated database retains executed test evidence separately from the demo.
Path("runtime/tests").mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite:///runtime/tests/" + uuid.uuid4().hex + ".db")
os.environ["EVIDENCE_PATH"] = "runtime/tests/evidence"
os.environ["APP_MODE"] = "demo"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from services.api.main import app
from services.api.audit import append_event, verify_chain
from services.api.database import Approval, AuditEvent, Batch, ExceptionCase, Run, Session, SessionLocal, User
from services.api.operations import process_run
from services.api.reports import safe_csv
from scripts.fixtures import make_fixtures, zip_package
from scripts.seed import seed


@pytest.fixture(scope="module", autouse=True)
def database():
    command.upgrade(Config("alembic.ini"), "head")
    seed()


@pytest.fixture
def client():
    with TestClient(app, headers={"Origin": "http://localhost:3000"}) as browser:
        yield browser


def login(client, user="demo-analyst"):
    response = client.post("/api/auth/demo", json={"user_id": user})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()


def test_auth_required_every_financial_api(client):
    for path in ("/api/dashboard", "/api/runs", "/api/batches", "/api/users", "/api/policies", "/api/audit", "/api/jobs"):
        assert client.get(path).status_code == 401


def test_audit_checkpoint_remains_valid_during_concurrent_append(monkeypatch):
    with SessionLocal() as db:
        original_scalars = db.scalars

        def concurrent_read(statement):
            events = list(original_scalars(statement))
            with SessionLocal.begin() as writer:
                append_event(writer, "test-concurrent", "audit.regression", "checkpoint")
            return iter(events)

        monkeypatch.setattr(db, "scalars", concurrent_read)
        assert verify_chain(db)
    with SessionLocal() as db:
        assert verify_chain(db)


def test_expired_session(client):
    login(client)
    with SessionLocal.begin() as db:
        from services.api.auth import token_hash
        session = db.get(Session, token_hash(client.cookies["fccs_session"]))
        session.expires = "2000-01-01T00:00:00+00:00"
    assert client.get("/api/session").status_code == 401


def test_csrf_and_origin_rejected(client):
    login(client)
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/runs", json={"gl_id": "x", "fccs_id": "x", "policy_id": "x"}).status_code == 403
    client.headers["Origin"] = "https://untrusted.example"
    assert client.post("/api/auth/demo", json={"user_id": "demo-admin"}).status_code == 403


def test_import_run_idempotency_and_exact_amount(client):
    login(client)
    policy, bundles = make_fixtures()
    ids = {}
    for side, (raw, manifest) in bundles.items():
        package = zip_package(raw, manifest)
        first = client.post("/api/batches", files={"file": ("source.zip", package)})
        second = client.post("/api/batches", files={"file": ("source.zip", package)})
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        ids[side] = first.json()["id"]
    body = {"gl_id": ids["GL"], "fccs_id": ids["FCCS"], "policy_id": policy["id"]}
    first = client.post("/api/runs", json=body).json()
    second = client.post("/api/runs", json=body).json()
    assert first["id"] == second["id"]
    assert first["result"] == second["result"]
    assert any(check["variance"] == "0.01" for check in first["result"]["checks"])
    assert first["state"] == "FAIL"


def test_entity_scoping_and_unauthorized_actions(client):
    login(client)
    run = client.get("/api/runs").json()[0]
    login(client, "demo-viewer")
    assert client.get("/api/runs").json() == []
    assert client.get(f"/api/runs/{run['id']}").status_code == 403
    assert client.get(f"/api/runs/{run['id']}/report/json").status_code == 403
    assert client.get(f"/api/batches/{run['gl_id']}/evidence").status_code == 403
    assert client.post("/api/runs", json={key: run[key] for key in ("gl_id", "fccs_id", "policy_id")}).status_code == 403
    assert client.post("/api/connections/test").status_code == 403


def test_interrupted_invalid_import_is_atomic(client):
    login(client)
    before = len(client.get("/api/batches").json())
    response = client.post("/api/batches", files={"file": ("broken.zip", b"PK not a complete archive")})
    assert response.status_code == 422
    assert len(client.get("/api/batches").json()) == before


def test_archive_path_traversal_rejected(client):
    login(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../data.csv", "bad")
        archive.writestr("manifest.json", "{}")
    assert client.post("/api/batches", files={"file": ("x.zip", stream.getvalue())}).status_code == 422


def test_incomplete_manifest_returns_blocked_run(client):
    login(client)
    policy, bundles = make_fixtures()
    raw, manifest = bundles["FCCS"]
    manifest["complete"] = False
    batch = client.post("/api/batches", files={"file": ("incomplete.zip", zip_package(raw, manifest))}).json()
    gl = next(item for item in client.get("/api/batches").json() if item["side"] == "GL")
    run = client.post("/api/runs", json={"gl_id": gl["id"], "fccs_id": batch["id"], "policy_id": policy["id"]}).json()
    assert run["state"] == "BLOCKED"
    assert not any(check["rule"] == "C04 Reconciliation" for check in run["result"]["checks"])


def test_four_eyes_policy_and_immutability(client):
    login(client)
    policy, _ = make_fixtures()
    policy["id"] = "test-proposed-policy"
    assert client.post("/api/policies", json=policy).status_code == 200
    assert client.post(f"/api/policies/{policy['id']}/approve").status_code == 403
    login(client, "demo-approver")
    assert client.post(f"/api/policies/{policy['id']}/approve").status_code == 200
    assert client.post(f"/api/policies/{policy['id']}/approve").status_code == 409
    with SessionLocal() as db:
        with pytest.raises(Exception):
            db.execute(text("UPDATE policies SET author='changed' WHERE id='demo-policy-v1'"))
        db.rollback()


def test_case_assignment_concurrency_and_audit(client):
    login(client)
    case = next(item for item in client.get("/api/exceptions").json() if item["state"] == "NEW")
    body = {"owner": "demo-analyst", "state": "ASSIGNED", "comment": "Investigating exact-cent evidence", "version": case["version"]}
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 200
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 409
    history = client.get(f"/api/exceptions/{case['id']}/history").json()
    assert history[-1]["payload"]["from"] == "NEW"
    assert history[-1]["payload"]["to"] == "ASSIGNED"
    body.update(state="IN_REVIEW", version=case["version"] + 1)
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 200
    body.update(state="ACCEPTED_RISK", version=case["version"] + 2)
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 403


def test_duplicate_worker_execution_and_chain(client):
    login(client)
    run_id = client.get("/api/runs").json()[0]["id"]
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(process_run, [run_id] * 3))
    with SessionLocal() as db:
        assert db.get(Run, run_id).attempts == 1
        assert verify_chain(db)
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.target == run_id, AuditEvent.action == "validation.completed")))
        assert len(events) == 1


def test_report_bundle_and_csv_safety(client):
    login(client)
    run_id = client.get("/api/runs").json()[0]["id"]
    response = client.get(f"/api/runs/{run_id}/report/zip")
    assert response.status_code == 200
    from packages.reconciliation.contracts import digest
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        checksums = json.loads(archive.read("SHA256SUMS.json"))
        assert all(digest(archive.read(name)) == value for name, value in checksums.items())
        assert archive.read("summary.pdf").startswith(b"%PDF")
        document = json.loads(archive.read("report.json"))
        assert document["run_id"] == run_id
    for unsafe in ("=WEBSERVICE('x')", "+1", "-2", "@SUM(A1)", "  =1"):
        assert safe_csv(unsafe).startswith("'")


def test_mock_connection_never_claims_live_success(client):
    login(client, "demo-admin")
    result = client.post("/api/connections/test").json()
    assert result["status"] == "MOCK_ONLY"
    assert "No Oracle connection" in result["message"]


def test_initial_baseline_can_pass_and_resolve_with_independent_review(client):
    login(client)
    runs = client.get("/api/runs").json()
    baseline = next(run for run in runs if run["state"] == "PASS")
    case = next(item for item in client.get("/api/exceptions").json() if item["state"] == "NEW")
    body = {"owner": "demo-analyst", "state": "ASSIGNED", "comment": "Reviewing source correction", "version": case["version"]}
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 200
    body.update(state="IN_REVIEW", version=case["version"] + 1)
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 200
    login(client, "demo-approver")
    body.update(state="RESOLVED", version=case["version"] + 2, evidence_run_id=baseline["id"])
    assert client.patch(f"/api/exceptions/{case['id']}", json=body).status_code == 200
    original = client.get(f"/api/runs/{case['run_id']}").json()
    assert original["state"] in {"FAIL", "BLOCKED"}


def test_interrupted_worker_rolls_back_and_recovers(client, monkeypatch):
    login(client)
    from services.api import operations
    from services.api.database import PolicyRecord
    from sqlalchemy.exc import OperationalError
    with SessionLocal.begin() as db:
        original = db.scalar(select(Run))
        run = operations.request_run(db, db.get(User, "demo-analyst"), original.gl_id, original.fccs_id,
                                     original.policy_id, occurrence="failure-injection")
        run_id = run.id
    real_validation = operations.validate
    def interrupted(*args, **kwargs):
        raise OperationalError("Injected interruption", {}, None)
    monkeypatch.setattr(operations, "validate", interrupted)
    with pytest.raises(OperationalError):
        process_run(run_id)
    with SessionLocal() as db:
        assert db.get(Run, run_id).state == "QUEUED"
        assert db.get(Run, run_id).result is None
        assert not list(db.scalars(select(ExceptionCase).where(ExceptionCase.run_id == run_id)))
    monkeypatch.setattr(operations, "validate", real_validation)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(process_run, [run_id] * 3))
    with SessionLocal() as db:
        assert db.get(Run, run_id).state in {"PASS", "FAIL", "BLOCKED"}
        assert db.get(Run, run_id).attempts == 1


def test_scheduler_creates_one_durable_occurrence(client):
    login(client)
    from services.api.database import Schedule
    from services.api.worker import create_due_runs
    from datetime import datetime, timezone
    with SessionLocal.begin() as db:
        original = db.scalar(select(Run))
        db.add(Schedule(id="schedule-regression", name="Synthetic recheck", gl_id=original.gl_id,
                        fccs_id=original.fccs_id, policy_id=original.policy_id, interval_minutes=60,
                        next_due="2026-11-12T00:00:00+00:00", actor="demo-admin"))
    timestamp = datetime(2026, 11, 12, 1, tzinfo=timezone.utc)
    create_due_runs(timestamp)
    create_due_runs(timestamp)
    with SessionLocal() as db:
        schedule = db.get(Schedule, "schedule-regression")
        assert schedule.next_due == "2026-11-12T02:00:00+00:00"
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.target == schedule.id, AuditEvent.action == "schedule.executed")))
        assert len(events) == 1
