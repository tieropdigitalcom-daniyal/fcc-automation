"""Provision the first production administrator from secure operator environment."""
import os
from services.api.auth import oidc_subject
from services.api.audit import append_event
from services.api.database import SessionLocal, User
from sqlalchemy import select

with SessionLocal.begin() as db:
    if db.scalar(select(User.id).limit(1)):
        raise RuntimeError("Use authenticated administration after initial bootstrap")
    subject = os.environ["BOOTSTRAP_OIDC_SUBJECT"]
    name = os.environ["BOOTSTRAP_DISPLAY_NAME"]
    identifier = oidc_subject(subject)
    db.add(User(id=identifier, name=name, role="integration_admin", entities=["*"]))
    append_event(db, "operator-bootstrap", "user.provisioned", identifier, {"role": "integration_admin"})
