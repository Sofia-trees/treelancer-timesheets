"""Magic-link auth + JWT session tokens.

Flow:
  1. POST /auth/request-link {email}  -> issue a single-use token, email a link
     (or, in dev, return it). Only a SHA-256 hash of the token is stored.
  2. POST /auth/verify {token}        -> consume it, return a JWT session token.
  3. Bearer JWT on every request -> `current_user` resolves it.

No passwords anywhere.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import MagicLinkToken, User, UserRole

_settings = get_settings()
_ALGO = "HS256"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """SQLite stores DateTime(timezone=True) as naive; treat such values as UTC
    so comparisons against the aware `_now()` don't blow up. (Postgres returns
    aware datetimes and this is a no-op.)"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def issue_magic_link(db: Session, email: str) -> tuple[str, User] | None:
    """Create a single-use token for an existing, active user. Returns
    (raw_token, user) or None if no such user (caller stays vague to avoid
    leaking which emails exist)."""
    user = db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    if user is None:
        return None
    raw = secrets.token_urlsafe(32)
    db.add(
        MagicLinkToken(
            user_id=user.id,
            token_hash=_hash(raw),
            expires_at=_now() + timedelta(minutes=_settings.magic_link_ttl_minutes),
        )
    )
    db.commit()
    return raw, user


def verify_magic_link(db: Session, raw_token: str) -> str:
    """Consume a token and return a signed JWT session. Raises 400 on
    invalid/expired/already-used tokens."""
    row = db.scalar(select(MagicLinkToken).where(MagicLinkToken.token_hash == _hash(raw_token)))
    if row is None or row.consumed_at is not None or _as_utc(row.expires_at) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired login link")
    row.consumed_at = _now()
    db.commit()
    return _make_jwt(str(row.user_id))


def _make_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": _now() + timedelta(hours=_settings.jwt_ttl_hours),
        "iat": _now(),
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_ALGO)


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_role(*roles: UserRole):
    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return guard
