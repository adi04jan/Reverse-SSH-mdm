"""Verify the portal renders correctly when served under a subpath prefix.

Simulates the reverse proxy by sending X-Forwarded-Prefix (the proxy strips the
prefix from the path, so the app receives unprefixed paths — exactly what
TestClient sends).
"""
import os
import tempfile

tmp = tempfile.mkdtemp(prefix="portal-subpath-")
os.environ["PORTAL_DB_PATH"] = os.path.join(tmp, "portal.db")
os.environ["PORTAL_AUTHORIZED_KEYS_PATH"] = os.path.join(tmp, "authorized_keys")
os.environ["PORTAL_SECRET_KEY"] = "test-secret"
os.environ["PORTAL_PUBLIC_URL"] = "http://182.70.254.11:1010/reverse-ssh"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

with TestClient(app) as c:
    c.headers.update({"X-Forwarded-Prefix": "/reverse-ssh"})

    # Static mount must serve under the prefix (this is what broke with root_path).
    r = c.get("/static/style.css")
    assert r.status_code == 200, f"static not served: {r.status_code}"

    # Login page should reference prefixed assets and form action.
    r = c.get("/login")
    assert r.status_code == 200, r.text
    assert '/reverse-ssh/static/style.css' in r.text, "static not prefixed"
    assert 'action="/reverse-ssh/login"' in r.text, "form action not prefixed"

    # Login redirect should target the prefixed dashboard.
    r = c.post("/login", data={"username": "admin", "password": "admin"},
               follow_redirects=False)
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/reverse-ssh/", r.headers["location"]

    # Create a device + token, then check the install command uses PUBLIC_URL.
    r = c.post("/devices", data={"name": "pi", "os": "linux", "note": ""},
               follow_redirects=False)
    did = int(r.headers["location"].rstrip("/").split("/")[-1])
    assert r.headers["location"] == f"/reverse-ssh/devices/{did}"
    r = c.post(f"/devices/{did}/token", follow_redirects=False)
    token = r.headers["location"].split("token=")[1]
    r = c.get(f"/devices/{did}?token={token}")
    assert "http://182.70.254.11:1010/reverse-ssh/static/install.sh" in r.text, \
        "install command missing public_url"
    # Agent API still reachable at the unprefixed path inside the app.
    r = c.post("/api/agent/enroll", json={"token": token})
    assert r.status_code == 200, r.text

print("SUBPATH OK")
