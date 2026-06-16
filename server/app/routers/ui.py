"""Server-rendered HTML pages: dashboard and device detail."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..deps import require_user
from ..models import Device, EnrollmentToken, Tunnel, User, utcnow
from ..services import ssh_status
from ..templating import templates

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    devices = session.exec(select(Device)).all()
    rows = []
    for d in devices:
        tunnels = session.exec(select(Tunnel).where(Tunnel.device_id == d.id)).all()
        rows.append(
            {
                "device": d,
                "online": ssh_status.device_online(d.last_seen),
                "tunnel_count": len(tunnels),
                "enabled_count": sum(1 for t in tunnels if t.enabled),
            }
        )
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "rows": rows, "settings": settings},
    )


@router.get("/devices/{device_id}")
def device_detail(
    device_id: int,
    request: Request,
    token: Optional[str] = None,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    tunnels = session.exec(
        select(Tunnel).where(Tunnel.device_id == device_id).order_by(Tunnel.remote_port)
    ).all()

    # Is there an unused enrollment token outstanding for this device?
    has_active_token = bool(
        session.exec(
            select(EnrollmentToken)
            .where(EnrollmentToken.device_id == device_id)
            .where(EnrollmentToken.used == False)  # noqa: E712
        ).first()
    )

    # Externally reachable base URL for install commands (honours subpath).
    portal_url = settings.public_url or str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "device.html",
        {
            "request": request,
            "user": user,
            "device": device,
            "tunnels": tunnels,
            "online": ssh_status.device_online(device.last_seen),
            "new_token": token,          # shown once right after issuing
            "has_active_token": has_active_token,
            "portal_url": portal_url,
            "settings": settings,
        },
    )
