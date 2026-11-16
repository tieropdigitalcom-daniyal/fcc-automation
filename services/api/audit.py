from sqlalchemy import select, update
from .database import AuditEvent, AuditHead, utcnow
from packages.reconciliation.contracts import digest


def append_event(db, actor, action, target, payload=None):
    # The UPDATE acquires the database write lock before reading the chain head.
    db.execute(update(AuditHead).where(AuditHead.id == 1).values(sequence=AuditHead.sequence + 1))
    head = db.execute(select(AuditHead).where(AuditHead.id == 1).with_for_update()).scalar_one()
    document = {"sequence": head.sequence, "actor": actor, "action": action, "target": target,
                "payload": payload or {}, "created": utcnow(), "previous_hash": head.hash}
    event_hash = digest(document)
    db.add(AuditEvent(**document, hash=event_hash))
    head.hash = event_hash
    db.flush()


def verify_chain(db):
    # Capture one committed checkpoint before scanning. Append-only events at or
    # below it cannot change, even when other requests extend the chain during
    # verification under PostgreSQL READ COMMITTED or SQLite legacy reads.
    head_sequence, head_hash = db.execute(
        select(AuditHead.sequence, AuditHead.hash).where(AuditHead.id == 1)
    ).one()
    previous = "0" * 64
    expected_sequence = 1
    for event in db.scalars(select(AuditEvent).where(AuditEvent.sequence <= head_sequence).order_by(AuditEvent.sequence)):
        document = {key: getattr(event, key) for key in ("sequence", "actor", "action", "target", "payload", "created", "previous_hash")}
        if event.sequence != expected_sequence or event.previous_hash != previous or digest(document) != event.hash:
            return False
        previous = event.hash
        expected_sequence += 1
    return head_hash == previous and head_sequence == expected_sequence - 1
