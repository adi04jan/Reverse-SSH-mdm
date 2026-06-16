"""Device management: create, delete, issue enrollment token (form-post UI)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlmodel import Session, delete, select

from ..audit import log
from ..auth import new_token
from ..config import settings
from ..db import get_session
from ..deps import require_user
from ..models import Device, EnrollmentToken, Tunnel, User, utcnow
from ..services import authorized_keys
from ..urls import redirect

router = APIRouter()


@router.post("/devices")
def create_device(
    request: Request,
    name: str = Form(...),
    os: str = Form("linux"),
    note: str = Form(""),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "Device name is required")
    if session.exec(select(Device).where(Device.name == name)).first():
        raise HTTPException(409, f"Device '{name}' already exists")
    device = Device(name=name, os=os, note=note.strip() or None)
    session.add(device)
    session.commit()
    session.refresh(device)
    log(session, user.username, "device.create", name)
    return redirect(request, f"/devices/{device.id}")


@router.post("/devices/{device_id}/token")
def issue_token(
    device_id: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    # Invalidate any previous unused tokens for this device.
    for old in session.exec(
        select(EnrollmentToken)
        .where(EnrollmentToken.device_id == device_id)
        .where(EnrollmentToken.used == False)  # noqa: E712
    ).all():
        old.used = True
        session.add(old)

    token = new_token()
    session.add(
        EnrollmentToken(
            token=token,
            device_id=device_id,
            expires_at=utcnow() + timedelta(seconds=settings.enroll_token_ttl),
        )
    )
    session.commit()
    log(session, user.username, "device.token", device.name)
    # Surface the token once via a query param so the detail page can show it.
    return redirect(request, f"/devices/{device_id}?token={token}")


@router.post("/devices/{device_id}/delete")
def delete_device(
    device_id: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    name = device.name
    session.exec(delete(Tunnel).where(Tunnel.device_id == device_id))
    session.exec(delete(EnrollmentToken).where(EnrollmentToken.device_id == device_id))
    session.delete(device)
    session.commit()
    authorized_keys.safe_write(session)
    log(session, user.username, "device.delete", name)
    return redirect(request, "/")
