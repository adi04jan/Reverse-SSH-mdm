"""Database models (SQLModel).

Tables:
  - User            : portal logins (a few trusted users)
  - Device          : an enrolled test device + its SSH public key
  - EnrollmentToken : one-time, short-lived token used by an agent to enroll
  - Tunnel          : a port assignment (reverse tunnel) for a device
  - AuditLog        : append-only record of meaningful actions
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TunnelKind(str, Enum):
    ssh = "ssh"   # forwards the device's SSH port (interactive shell / scp)
    tcp = "tcp"   # forwards an arbitrary TCP service on the device


# Default ssh options for the rendered connect command. Forces password auth to
# the device (skips offering local keys) — handy for test devices that use a
# password login. Editable per tunnel from the device page.
DEFAULT_SSH_OPTS = "-o PubkeyAuthentication=no -o PreferredAuthentications=password"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    pw_hash: str
    role: str = "admin"
    created_at: datetime = Field(default_factory=utcnow)


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    os: str = "linux"                       # linux | windows | other
    pubkey: Optional[str] = None            # OpenSSH public key line (set at enroll)
    api_key_hash: Optional[str] = None      # hash of the long-lived device API key
    enrolled: bool = False
    last_seen: Optional[datetime] = None    # last heartbeat
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class EnrollmentToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    expires_at: datetime
    used: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Tunnel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    remote_port: int = Field(index=True, unique=True)   # port on the VPS public IP
    local_host: str = "localhost"                       # target host as seen by device
    local_port: int = 22                                # target port on the device
    kind: TunnelKind = TunnelKind.ssh
    enabled: bool = True
    label: Optional[str] = None
    # Connect-command overrides (used to render the copy-able SSH command in the
    # UI only; they do not affect the tunnel itself). connect_user is the login
    # name on the device; ssh_opts are extra `ssh` flags (default: force password).
    connect_user: Optional[str] = None
    ssh_opts: str = DEFAULT_SSH_OPTS
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str                       # username or "device:<name>" or "system"
    action: str
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
