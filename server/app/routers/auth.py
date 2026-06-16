"""Login / logout (session-cookie based)."""
from fastapi import APIRouter, Depends, Form, Request
from sqlmodel import Session

from ..audit import log
from ..auth import authenticate
from ..db import get_session
from ..templating import templates
from ..urls import redirect

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = authenticate(session, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    request.session["uid"] = user.id
    log(session, user.username, "login")
    return redirect(request, "/")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect(request, "/login")
