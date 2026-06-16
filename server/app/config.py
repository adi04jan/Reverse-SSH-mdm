"""Application configuration.

Values are read from environment variables (prefix ``PORTAL_``) or a ``.env``
file living next to the server. See ``deploy/setup_vps.sh`` for production values.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository / server base directory (…/server)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PORTAL_",
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- How devices reach the VPS (handed to agents during enrollment) ---
    vps_host: str = "182.70.254.11"      # public IP / hostname devices dial out to
    vps_ssh_port: int = 2201             # admin sshd port on the VPS
    tunnel_user: str = "tunnel"          # locked-down user that owns reverse tunnels

    # Address tunnels bind to on the server. "127.0.0.1" = reachable only by
    # SSH-jumping through the server (recommended for a home box behind a router).
    # "0.0.0.0" = bound on all interfaces (needs GatewayPorts + router forward).
    tunnel_bind: str = "127.0.0.1"
    # A real login account (with a shell) used to ProxyJump into the server to
    # reach the loopback tunnels — NOT the locked-down tunnel_user.
    ssh_jump_user: str = ""
    ssh_jump_port: int = 2201

    # --- Reverse-tunnel port pool (bound on the public IP via GatewayPorts) ---
    port_range_start: int = 20000
    port_range_end: int = 29999

    # --- Filesystem locations ---
    db_path: str = str(BASE_DIR / "data" / "portal.db")
    # authorized_keys file for the tunnel user that the portal rewrites.
    authorized_keys_path: str = "/home/tunnel/.ssh/authorized_keys"

    # --- Web app ---
    secret_key: str = "change-me-in-production"   # session signing key
    session_max_age: int = 60 * 60 * 12           # 12h cookies
    enroll_token_ttl: int = 60 * 30               # enrollment token valid 30 min
    heartbeat_online_window: int = 90             # seconds before a device is "offline"

    # Subpath the portal is served under, when behind a shared web server
    # (e.g. "/reverse-ssh" for http://host:1010/reverse-ssh). Empty for root.
    base_path: str = ""
    # Externally reachable base URL, used to render device install commands.
    # e.g. "http://182.70.254.11:1010/reverse-ssh". Empty => derive from request.
    public_url: str = ""

    # First-run bootstrap admin (only used if no users exist yet).
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str = "admin"       # change immediately after first login

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, v: str) -> str:
        v = (v or "").strip().rstrip("/")
        if v and not v.startswith("/"):
            v = "/" + v
        return v

    @field_validator("public_url")
    @classmethod
    def _normalize_public_url(cls, v: str) -> str:
        return (v or "").strip().rstrip("/")

    @property
    def port_pool(self) -> range:
        return range(self.port_range_start, self.port_range_end + 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
