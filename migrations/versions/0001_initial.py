"""Initial persistent schema and append-only evidence guards."""
from alembic import op
from services.api.database import Base

revision = "0001"
down_revision = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute("INSERT INTO audit_head (id, sequence, hash) VALUES (1, 0, '" + "0" * 64 + "')")
    immutable = ("audit_events", "policies", "approvals", "batches")
    if bind.dialect.name == "sqlite":
        for table in immutable:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only evidence'); END")  # nosec B608 -- fixed table allowlist
        op.execute("CREATE TRIGGER immutable_run BEFORE UPDATE ON runs WHEN OLD.state IN ('PASS','FAIL','BLOCKED') BEGIN SELECT RAISE(ABORT, 'Completed run is immutable'); END")
        op.execute("CREATE TRIGGER prevent_run_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'Runs are retained'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Append-only evidence'; END $$")
        for table in immutable:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation()")  # nosec B608 -- fixed table allowlist
        op.execute("CREATE FUNCTION protect_completed_run() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP = 'DELETE' OR OLD.state IN ('PASS','FAIL','BLOCKED') THEN RAISE EXCEPTION 'Completed run is immutable'; END IF; RETURN NEW; END $$")
        op.execute("CREATE TRIGGER immutable_run BEFORE UPDATE OR DELETE ON runs FOR EACH ROW EXECUTE FUNCTION protect_completed_run()")


def downgrade():
    raise RuntimeError("Evidence schema rollback requires a reviewed restore procedure")
