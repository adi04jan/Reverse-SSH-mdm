"""End-to-end smoke test of the portal using FastAPI's TestClient.

Exercises: login -> create device -> issue token -> agent enroll ->
get state -> create tunnel -> state reflects it -> authorized_keys written.
"""
import os
import tempfile

tmp = tempfile.mkdtemp(prefix="portal-smoke-")
os.environ["PORTAL_DB_PATH"] = os.path.join(tmp, "portal.db")
os.environ["PORTAL_AUTHORIZED_KEYS_PATH"] = os.path.join(tmp, "authorized_keys")
os.environ["PORTAL_SECRET_KEY"] = "test-secret"
os.environ["PORTAL_VPS_HOST"] = "182.70.254.11"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

with TestClient(app) as c:
    # 1) login
    r = c.post("/login", data={"username": "admin", "password": "admin"},
               follow_redirects=False)
    assert r.status_code == 303, r.text
    assert "rsshp_session" in c.cookies, "session cookie set"

    # 2) create device
    r = c.post("/devices", data={"name": "test-pi", "os": "linux", "note": ""},
               follow_redirects=False)
    assert r.status_code == 303, r.text
    device_url = r.headers["location"]
    device_id = int(device_url.rstrip("/").split("/")[-1])

    # 3) issue enrollment token
    r = c.post(f"/devices/{device_id}/token", follow_redirects=False)
    assert r.status_code == 303, r.text
    token = r.headers["location"].split("token=")[1]
    assert token

    # 4) agent enrolls (no session cookie needed; token-based)
    r = c.post("/api/agent/enroll", json={"token": token, "hostname": "pi", "os": "linux"})
    assert r.status_code == 200, r.text
    enroll = r.json()
    api_key = enroll["api_key"]
    assert enroll["vps_host"] == "182.70.254.11"
    assert "PRIVATE KEY" in enroll["private_key"]

    # token is single-use now
    r = c.post("/api/agent/enroll", json={"token": token})
    assert r.status_code == 401, "token should be consumed"

    # 5) agent gets (empty) state
    h = {"Authorization": f"Bearer {api_key}"}
    r = c.get("/api/agent/state", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tunnels"] == []

    # 6) assign a tunnel (auto port)
    r = c.post(f"/devices/{device_id}/tunnels",
               data={"remote_port": "", "kind": "ssh", "local_host": "localhost",
                     "local_port": "22", "label": "shell"},
               follow_redirects=False)
    assert r.status_code == 303, r.text

    # 7) state now reflects it
    r = c.get("/api/agent/state", headers=h)
    tunnels = r.json()["tunnels"]
    assert len(tunnels) == 1, tunnels
    port = tunnels[0]["remote_port"]
    assert 20000 <= port <= 29999

    # 8) authorized_keys file written with restrict + permitlisten
    with open(os.environ["PORTAL_AUTHORIZED_KEYS_PATH"]) as f:
        ak = f.read()
    assert "no-pty" in ak and f'permitlisten="127.0.0.1:{port}"' in ak, ak

    # 9) heartbeat + dashboard status
    r = c.post("/api/agent/heartbeat", headers=h, json={"active_ports": [port]})
    assert r.status_code == 200
    r = c.get("/api/status")
    assert r.status_code == 200
    assert r.json()["devices"][0]["online"] is True

    # 10) delete tunnel -> removed from authorized_keys
    r = c.get(device_url)  # find tunnel id via state instead
    r = c.post(f"/tunnels/1/delete", follow_redirects=False)
    assert r.status_code == 303
    with open(os.environ["PORTAL_AUTHORIZED_KEYS_PATH"]) as f:
        ak2 = f.read()
    assert f'permitlisten="127.0.0.1:{port}"' not in ak2

print("SMOKE OK")
