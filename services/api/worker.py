"""Durable dispatcher, transactional execution and observable notification outbox."""
from datetime import datetime, timedelta, timezone

import httpx
from celery import Celery
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from .audit import append_event
from .auth import can_access
from .config import settings
from .database import Batch, Notification, Run, Schedule, SessionLocal, User, utcnow
from .operations import process_run, request_run

celery = Celery("fccs", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
                   broker_connection_retry_on_startup=True, task_time_limit=300,
                   beat_schedule={"dispatch": {"task": "fccs.dispatch", "schedule": 30.0}})


@celery.task(name="fccs.execute", autoretry_for=(OperationalError,), retry_backoff=True, max_retries=5)
def execute_run(run_id):
    process_run(run_id)


def create_due_runs(now=None):
    now = now or datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        schedules = db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_due <= now.isoformat())
                              .with_for_update(skip_locked=True)).all()
        for schedule in schedules:
            actor = db.get(User, schedule.actor)
            gl, fccs = db.get(Batch, schedule.gl_id), db.get(Batch, schedule.fccs_id)
            if not actor or not actor.active or actor.role != "integration_admin" or not can_access(actor, gl.entities + fccs.entities):
                schedule.enabled = False
                append_event(db, "scheduler", "schedule.access_revoked", schedule.id)
                continue
            occurrence = schedule.id + "/" + schedule.next_due
            request_run(db, actor, gl.id, fccs.id, schedule.policy_id, occurrence=occurrence)
            schedule.next_due = (now + timedelta(minutes=schedule.interval_minutes)).isoformat()
            append_event(db, "scheduler", "schedule.executed", schedule.id, {"occurrence": occurrence})


@celery.task(name="fccs.dispatch")
def dispatch():
    create_due_runs()
    with SessionLocal() as db:
        for run_id in db.scalars(select(Run.id).where(Run.state == "QUEUED")):
            execute_run.delay(run_id)
        for notification_id in db.scalars(select(Notification.id).where(Notification.state == "PENDING")):
            deliver_notification.delay(notification_id)


@celery.task(name="fccs.notify", autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=5)
def deliver_notification(notification_id):
    with SessionLocal.begin() as db:
        notification = db.scalar(select(Notification).where(Notification.id == notification_id).with_for_update())
        if not notification or notification.state in {"DELIVERED", "UNCONFIGURED", "FAILED", "BLOCKED"}:
            return
        if not settings.notification_url:
            notification.state = "UNCONFIGURED"
            return
        if not settings.notification_url.startswith("https://"):
            notification.state = "BLOCKED"
            return
        run = db.get(Run, notification.run_id)
        notification.attempts += 1
        # A receiving endpoint deduplicates this stable id after an ambiguous response.
        try:
            response = httpx.post(settings.notification_url, timeout=15, follow_redirects=False,
                                  headers={"Idempotency-Key": notification.id},
                                  json={"event_id": notification.id, "run_id": run.id, "status": run.state})
            response.raise_for_status()
        except httpx.HTTPError:
            notification.state = "FAILED" if notification.attempts >= 5 else "PENDING"
            append_event(db, "worker", "notification.failed", notification.id, {"attempts": notification.attempts})
            db.commit()
            raise
        notification.state = "DELIVERED"
        append_event(db, "worker", "notification.delivered", notification.id)
