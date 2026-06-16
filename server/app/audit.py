"""Tiny helper for writing audit-log entries."""
from typing import Optional

from sqlmodel import Session

from .models import AuditLog


def log(session: Session, actor: str, action: str, detail: Optional[str] = None) -> None:
    session.add(AuditLog(actor=actor, action=action, detail=detail))
    session.commit()
