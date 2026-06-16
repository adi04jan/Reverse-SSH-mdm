"""FastAPI application factory + wiring."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import ensure_bootstrap_admin
from .config import settings
from .db import engine, init_db
from .deps import LoginRequired
from .routers import agent, auth, devices, status, tunnels, ui

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        ensure_bootstrap_admin(session)
    yield


app = FastAPI(title="Reverse SSH Tunnel Portal", lifespan=lifespan)
# NOTE: we intentionally don't set root_path; the proxy strips the subpath and
# the app runs at root. URL prefixing for the browser is handled via the
# X-Forwarded-Prefix header (see app/urls.py). Setting root_path here would
# break the /static mount.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    same_site="lax",
    # Distinct cookie name so it doesn't collide with other apps sharing the
    # same host:port (e.g. Nextcloud on the same server).
    session_cookie="rsshp_session",
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(LoginRequired)
async def _login_required_handler(request: Request, exc: LoginRequired):
    from .urls import base_path

    return RedirectResponse(f"{base_path(request)}/login", status_code=303)


# HTML
app.include_router(auth.router)
app.include_router(ui.router)
app.include_router(devices.router)
app.include_router(tunnels.router)
# JSON
app.include_router(agent.router)
app.include_router(status.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
