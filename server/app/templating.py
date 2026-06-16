"""Shared Jinja2 templates instance.

A context processor injects ``base`` (the subpath prefix) into every template so
links/forms/static refs render correctly whether the portal is served at the
site root or under a prefix like ``/reverse-ssh``.
"""
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .urls import base_path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _base_path(request: Request) -> dict:
    return {"base": base_path(request)}


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[_base_path],
)
