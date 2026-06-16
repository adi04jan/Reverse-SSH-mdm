"""Determine connectivity status.

A device is "online" if its last heartbeat is recent. A tunnel is "up" if its
remote port is actually listening on the VPS (best-effort via ``ss``/``netstat``).
"""
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

from ..config import settings


def device_online(last_seen: Optional[datetime]) -> bool:
    if last_seen is None:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    return age <= settings.heartbeat_online_window


def listening_ports() -> set[int]:
    """Return the set of TCP ports currently in LISTEN state on the host.

    Tries ``ss`` then ``netstat``. Returns an empty set if neither is available
    (e.g. local dev on Windows) — callers should treat that as "unknown".
    """
    for cmd in (["ss", "-ltn"], ["netstat", "-ltn"]):
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, check=False
            ).stdout
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
        ports: set[int] = set()
        for line in out.splitlines():
            # match the local-address column ending in :PORT
            m = re.search(r"[:.](\d+)\s", line)
            if m:
                ports.add(int(m.group(1)))
        if ports:
            return ports
    return set()
