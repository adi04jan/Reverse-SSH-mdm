"""Connectivity status as JSON, used by the dashboard for live updates."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_user_api
from ..models import Device, Tunnel, User
from ..services import ssh_status

router = APIRouter(prefix="/api")


@router.get("/status")
def status(
    user: User = Depends(require_user_api),
    session: Session = Depends(get_session),
):
    listening = ssh_status.listening_ports()  # empty set => "unknown" (e.g. dev box)
    have_listen_info = bool(listening)

    devices = []
    for d in session.exec(select(Device)).all():
        tunnels = session.exec(
            select(Tunnel).where(Tunnel.device_id == d.id)
        ).all()
        devices.append(
            {
                "id": d.id,
                "name": d.name,
                "online": ssh_status.device_online(d.last_seen),
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "tunnels": [
                    {
                        "id": t.id,
                        "remote_port": t.remote_port,
                        "enabled": t.enabled,
                        "up": (t.remote_port in listening) if have_listen_info else None,
                    }
                    for t in tunnels
                ],
            }
        )
    return {"devices": devices}
