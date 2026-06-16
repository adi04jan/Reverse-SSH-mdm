"""Render and atomically write the tunnel user's authorized_keys.

The portal is the source of truth. On every device/tunnel change we rebuild the
whole file from the database. Each enrolled device gets one line:

    no-agent-forwarding,no-x11-forwarding,no-pty,permitlisten="127.0.0.1:20001" ssh-ed25519 AAAA... device:my-pi

The device key may ONLY open the reverse-forward ports listed via
``permitlisten``; combined with the server-side ``Match User tunnel`` block
(remote-forward-only, ForceCommand nologin) the account cannot get a shell or
forward anything else. The bind address comes from ``settings.tunnel_bind``
(127.0.0.1 by default). Binding to 0.0.0.0 additionally requires
``GatewayPorts clientspecified`` in sshd_config.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..models import Device, Tunnel

HEADER = "# Managed by reverse-ssh portal. DO NOT EDIT BY HAND.\n"


def render(session: Session) -> str:
    lines = [HEADER]
    devices = session.exec(select(Device).where(Device.enrolled == True)).all()  # noqa: E712
    for device in devices:
        if not device.pubkey:
            continue
        tunnels = session.exec(
            select(Tunnel)
            .where(Tunnel.device_id == device.id)
            .where(Tunnel.enabled == True)  # noqa: E712
        ).all()
        # NOTE: we do NOT use "restrict" here. On OpenSSH 8.2 (Ubuntu 20.04),
        # "restrict" disables port-forwarding and permitlisten fails to re-enable
        # remote (-R) forwarding, so tunnels are refused. Instead we list the
        # specific lock-downs and rely on permitlisten (per-device port limit)
        # plus the server-side `Match User tunnel` block (AllowTcpForwarding
        # remote, no pty, ForceCommand nologin) for defense in depth.
        opts = ["no-agent-forwarding", "no-x11-forwarding", "no-pty"]
        for t in sorted(tunnels, key=lambda x: x.remote_port):
            opts.append(f'permitlisten="{settings.tunnel_bind}:{t.remote_port}"')
        # device.pubkey already contains "<type> <base64> [comment]".
        lines.append(f"{','.join(opts)} {device.pubkey.strip()}\n")
    return "".join(lines)


def write(session: Session) -> str:
    """Render from DB and atomically replace the authorized_keys file.

    Returns the path written. Best-effort chmod to 600. If the directory does
    not exist (e.g. running off-VPS during local dev) the call still renders but
    skips the write, raising FileNotFoundError to the caller's discretion.
    """
    content = render(session)
    target = Path(settings.authorized_keys_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".authkeys.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass  # not POSIX (local dev on Windows) — ignore
    return str(target)


def safe_write(session: Session) -> Optional[str]:
    """Like ``write`` but swallows filesystem errors (useful in local dev).

    Returns the path on success, or None if the file could not be written.
    """
    try:
        return write(session)
    except OSError:
        return None
