"""Auth endpoints: request a magic link, verify it, and read the current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import LinkRequest, LinkResponse, TokenResponse, UserOut, VerifyRequest

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()


@router.post("/request-link", response_model=LinkResponse)
def request_link(body: LinkRequest, db: Session = Depends(get_db)) -> LinkResponse:
    result = auth.issue_magic_link(db, body.email)
    # Stay vague either way so we don't reveal which emails are registered.
    generic = "If that email is registered, a sign-in link has been sent."
    if result is None:
        return LinkResponse(detail=generic)
    raw, _user = result
    link = f"{_settings.frontend_url}/login/verify?token={raw}"
    if _settings.expose_magic_link:
        return LinkResponse(detail=generic, magic_link=link)
    # TODO(prod): send `link` via the transactional email provider here.
    return LinkResponse(detail=generic)


@router.post("/verify", response_model=TokenResponse)
def verify(body: VerifyRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return TokenResponse(access_token=auth.verify_magic_link(db, body.token))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth.current_user)) -> User:
    return user
