"""FastAPI dependencies: session-based user auth and device bearer auth."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from .auth import verify_secret
from .db import get_session
from .models import Device, User


class LoginRequired(Exception):
    """Raised by browser dependencies to trigger a redirect to /login."""


def get_current_user(
    request: Request, session: Session = Depends(get_session)
) -> Optional[User]:
    uid = request.session.get("uid")
    if uid is None:
        return None
    return session.get(User, uid)


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """For HTML pages: redirect to /login when not authenticated."""
    if user is None:
        raise LoginRequired()
    return user


def require_user_api(user: Optional[User] = Depends(get_current_user)) -> User:
    """For JSON endpoints: return 401 instead of redirecting."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_device(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> Device:
    """Authenticate an agent via ``Authorization: Bearer <device-api-key>``."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    # API keys are random; scan enrolled devices and verify the hash.
    for device in session.exec(select(Device).where(Device.enrolled == True)).all():  # noqa: E712
        if device.api_key_hash and verify_secret(token, device.api_key_hash):
            return device
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device key")
