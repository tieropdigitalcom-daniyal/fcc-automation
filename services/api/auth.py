import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .config import settings
from .database import Session, User, get_db, utcnow

ROLES = {"viewer", "analyst", "reviewer", "finance_approver", "integration_admin", "auditor"}


def session_secret():
    if settings.session_secret:
        return settings.session_secret
    path = Path("runtime/session-secret")
    path.parent.mkdir(exist_ok=True)
    try:
        with path.open("x") as stream:
            stream.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    return path.read_text()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(db, user, response):
    token = secrets.token_urlsafe(48)
    session = Session(id=token_hash(token), user_id=user.id, csrf=secrets.token_urlsafe(32),
                      expires=(datetime.now(timezone.utc) + timedelta(hours=8)).isoformat())
    db.add(session)
    response.set_cookie("fccs_session", token, httponly=True, secure=settings.app_mode == "production",
                        samesite="lax", max_age=28800, path="/")
    return session


def check_origin(request):
    allowed = {settings.public_origin}
    if settings.app_mode == "demo":
        allowed |= {"http://localhost:3000", "http://127.0.0.1:3000"}
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403, "Request origin is not approved")


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("fccs_session")
    session = db.get(Session, token_hash(token)) if token else None
    if not session or session.expires <= utcnow():
        raise HTTPException(401, "Sign in required or session expired")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account is inactive")
    request.state.actor = user.id
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "CSRF token required")
    request.state.session = session
    return user


def require(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Your role cannot perform this action")


def can_access(user, entities):
    return bool(entities) and ("*" in user.entities or set(entities).issubset(user.entities))


def scoped(user, entities):
    if not can_access(user, entities):
        raise HTTPException(403, "The complete evidence scope is outside your entity access")


def oidc_subject(subject):
    return "oidc-" + token_hash(settings.oidc_issuer + "|" + subject)
