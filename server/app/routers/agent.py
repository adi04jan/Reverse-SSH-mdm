"""Agent-facing API: enrollment, desired-state polling, heartbeat (JSON)."""
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..audit import log
from ..auth import hash_secret, new_token
from ..config import settings
from ..db import get_session
from ..deps import require_device
from ..models import Device, EnrollmentToken, Tunnel, utcnow
from ..services import authorized_keys, keys

router = APIRouter(prefix="/api/agent")


class EnrollRequest(BaseModel):
    token: str
    hostname: Optional[str] = None
    os: Optional[str] = None


class EnrollResponse(BaseModel):
    device_id: int
    device_name: str
    api_key: str            # long-lived bearer key for state/heartbeat
    private_key: str        # OpenSSH private key for the reverse tunnel
    vps_host: str
    vps_ssh_port: int
    tunnel_user: str
    poll_interval: int = 15


class TunnelSpec(BaseModel):
    remote_port: int
    local_host: str
    local_port: int
    kind: str
    bind: str = "127.0.0.1"   # address to bind on the server (server policy)
    label: Optional[str] = None


class StateResponse(BaseModel):
    device_name: str
    vps_host: str
    vps_ssh_port: int
    tunnel_user: str
    poll_interval: int = 15
    tunnels: list[TunnelSpec]


class Heartbeat(BaseModel):
    active_ports: list[int] = []


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest, session: Session = Depends(get_session)):
    record = session.exec(
        select(EnrollmentToken).where(EnrollmentToken.token == req.token)
    ).first()
    if not record or record.used:
        raise HTTPException(401, "Invalid or already-used enrollment token")
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        from datetime import timezone

        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        raise HTTPException(401, "Enrollment token expired")

    device = session.get(Device, record.device_id)
    if not device:
        raise HTTPException(404, "Device not found")

    # Generate the per-device SSH keypair and a long-lived API key.
    pair = keys.generate_keypair(comment=f"device:{device.name}")
    api_key = new_token(32)

    device.pubkey = pair.public_openssh
    device.api_key_hash = hash_secret(api_key)
    device.enrolled = True
    if req.os:
        device.os = req.os
    if req.hostname:
        device.note = (device.note or "") + f" host={req.hostname}"
    record.used = True
    session.add(device)
    session.add(record)
    session.commit()

    # Authorize the new key (with whatever tunnels already exist).
    authorized_keys.safe_write(session)
    log(session, f"device:{device.name}", "device.enroll", req.hostname or "")

    return EnrollResponse(
        device_id=device.id,
        device_name=device.name,
        api_key=api_key,
        private_key=pair.private_openssh,
        vps_host=settings.vps_host,
        vps_ssh_port=settings.vps_ssh_port,
        tunnel_user=settings.tunnel_user,
        poll_interval=15,
    )


@router.get("/state", response_model=StateResponse)
def get_state(
    device: Device = Depends(require_device),
    session: Session = Depends(get_session),
):
    device.last_seen = utcnow()
    session.add(device)
    session.commit()

    tunnels = session.exec(
        select(Tunnel)
        .where(Tunnel.device_id == device.id)
        .where(Tunnel.enabled == True)  # noqa: E712
    ).all()
    return StateResponse(
        device_name=device.name,
        vps_host=settings.vps_host,
        vps_ssh_port=settings.vps_ssh_port,
        tunnel_user=settings.tunnel_user,
        tunnels=[
            TunnelSpec(
                remote_port=t.remote_port,
                local_host=t.local_host,
                local_port=t.local_port,
                kind=t.kind.value,
                bind=settings.tunnel_bind,
                label=t.label,
            )
            for t in tunnels
        ],
    )


@router.post("/heartbeat")
def heartbeat(
    hb: Heartbeat,
    device: Device = Depends(require_device),
    session: Session = Depends(get_session),
):
    device.last_seen = utcnow()
    session.add(device)
    session.commit()
    return {"ok": True}
