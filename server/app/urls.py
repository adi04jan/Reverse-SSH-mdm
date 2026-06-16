"""Subpath-aware URL helpers.

When the portal runs behind a shared web server under a prefix (e.g.
``/reverse-ssh``), the proxy strips that prefix before forwarding, so the app
itself always operates at the root (routes and the /static mount match normally).
The prefix only matters for URLs we hand back to the browser. We learn it from
the ``X-Forwarded-Prefix`` header the proxy sets (falling back to the configured
``PORTAL_BASE_PATH``). Templates get ``base`` injected via a context processor
(see ``templating.py``); routers use :func:`redirect` for form-post redirects.

NOTE: we deliberately do NOT set FastAPI's ``root_path`` — doing so prevents the
StaticFiles mount from matching.
"""
from fastapi import Request
from fastapi.responses import RedirectResponse

from .config import settings


def base_path(request: Request) -> str:
    prefix = request.headers.get("x-forwarded-prefix") or settings.base_path or ""
    return prefix.rstrip("/")


def redirect(request: Request, path: str, status_code: int = 303) -> RedirectResponse:
    if path.startswith("/"):
        path = base_path(request) + path
    return RedirectResponse(path, status_code=status_code)
