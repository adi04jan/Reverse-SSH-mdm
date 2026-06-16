"""Password hashing, token generation, and user bootstrap helpers."""
import secrets
from typing import Optional

import bcrypt
from sqlmodel import Session, select

from .config import settings
from .models import User


def _encode(raw: str) -> bytes:
    # bcrypt only considers the first 72 bytes; truncate explicitly to avoid errors.
    return raw.encode("utf-8")[:72]


def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(_encode(raw), bcrypt.gensalt()).decode("utf-8")


def verify_secret(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(raw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def new_token(nbytes: int = 24) -> str:
    """URL-safe random token (enrollment tokens, device API keys)."""
    return secrets.token_urlsafe(nbytes)


def authenticate(session: Session, username: str, password: str) -> Optional[User]:
    user = session.exec(select(User).where(User.username == username)).first()
    if user and verify_secret(password, user.pw_hash):
        return user
    return None


def ensure_bootstrap_admin(session: Session) -> None:
    """Create the first admin account if no users exist yet."""
    existing = session.exec(select(User)).first()
    if existing:
        return
    admin = User(
        username=settings.bootstrap_admin_user,
        pw_hash=hash_secret(settings.bootstrap_admin_password),
        role="admin",
    )
    session.add(admin)
    session.commit()
