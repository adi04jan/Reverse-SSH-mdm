"""Tunnel (port assignment) management — create / delete / toggle."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlmodel import Session, select

from ..audit import log
from ..config import settings
from ..db import get_session
from ..deps import require_user
from ..models import Device, Tunnel, TunnelKind, User
from ..services import authorized_keys
from ..urls import redirect

router = APIRouter()


def _used_ports(session: Session) -> set[int]:
    return {t.remote_port for t in session.exec(select(Tunnel)).all()}


def allocate_port(session: Session) -> int:
    used = _used_ports(session)
    for port in settings.port_pool:
        if port not in used:
            return port
    raise HTTPException(409, "No free ports left in the configured range")


@router.post("/devices/{device_id}/tunnels")
def create_tunnel(
    device_id: int,
    request: Request,
    remote_port: str = Form(""),
    local_host: str = Form("localhost"),
    local_port: int = Form(22),
    kind: TunnelKind = Form(TunnelKind.ssh),
    label: str = Form(""),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")

    if remote_port.strip():
        port = int(remote_port)
        if port not in settings.port_pool:
            raise HTTPException(
                400,
                f"Port must be within {settings.port_range_start}-{settings.port_range_end}",
            )
        if port in _used_ports(session):
            raise HTTPException(409, f"Port {port} is already assigned")
    else:
        port = allocate_port(session)

    tunnel = Tunnel(
        device_id=device_id,
        remote_port=port,
        local_host=local_host.strip() or "localhost",
        local_port=local_port,
        kind=kind,
        label=label.strip() or None,
    )
    session.add(tunnel)
    session.commit()
    authorized_keys.safe_write(session)
    log(session, user.username, "tunnel.create", f"{device.name}:{port}->{local_port}")
    return redirect(request, f"/devices/{device_id}")


@router.post("/tunnels/{tunnel_id}/toggle")
def toggle_tunnel(
    tunnel_id: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    tunnel = session.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(404, "Tunnel not found")
    tunnel.enabled = not tunnel.enabled
    session.add(tunnel)
    session.commit()
    authorized_keys.safe_write(session)
    state = "enable" if tunnel.enabled else "disable"
    log(session, user.username, f"tunnel.{state}", str(tunnel.remote_port))
    return redirect(request, f"/devices/{tunnel.device_id}")


@router.post("/tunnels/{tunnel_id}/delete")
def delete_tunnel(
    tunnel_id: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    tunnel = session.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(404, "Tunnel not found")
    device_id = tunnel.device_id
    port = tunnel.remote_port
    session.delete(tunnel)
    session.commit()
    authorized_keys.safe_write(session)
    log(session, user.username, "tunnel.delete", str(port))
    return redirect(request, f"/devices/{device_id}")
