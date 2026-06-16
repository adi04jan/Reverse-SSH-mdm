# Reverse SSH Tunnel Portal

A web portal to **create, manage, and delete reverse SSH tunnels** for test
devices that sit behind NAT (no router port-forwarding). Each device runs a small
agent that dials out to your VPS and opens `ssh -R` tunnels; the portal decides
which device gets which port and you reach the device at `VPS_IP:PORT`.

```
  Test device (behind NAT)            VPS (public IP)              You
  ┌───────────────────┐   ssh -R     ┌──────────────────┐  ssh   ┌──────────┐
  │ agent.py (poll)   │ ───────────▶ │ tunnel user      │ ◀───── │ laptop   │
  │  ssh -R :PORT…    │              │ sshd GatewayPorts │        │          │
  └───────────────────┘   HTTPS poll └──────────────────┘        └──────────┘
              ▲  desired state / heartbeat  │  authorized_keys
              └─────────────────────────────┘  (managed by portal)
```

## How it works

1. **Add a device** in the portal and **generate a one-time enrollment token**.
2. **Run the installer** on the device with that token. The agent registers,
   receives a per-device SSH key + API key, and installs itself as a service.
3. **Assign a tunnel** (a VPS port → a port on the device). The portal updates
   the tunnel user's `authorized_keys` (`restrict` + `permitlisten`) and the
   agent opens the `ssh -R` on its next poll — no device interaction needed.
4. **Connect**: for an SSH tunnel, `ssh USER@VPS_IP -p PORT`; for an arbitrary
   TCP tunnel, point your client at `VPS_IP:PORT`.
5. **Disable/delete** a tunnel and the agent tears it down within one poll.

## Server setup (on the VPS)

```bash
git clone <this repo> && cd Reverse-SSH-mdm/server
sudo bash deploy/setup_vps.sh        # creates tunnel user, sshd config, venv, systemd
```

By default the app installs to `/var/www/reverse-ssh-portal`, runs as the
`tunnel` user on `127.0.0.1:8011`, and is served under the subpath
`/reverse-ssh`. The script writes `<install dir>/.env` with a generated admin
password and secret key.

### Serving under a subpath alongside your other sites (recommended)

If you already reach apps as `IP:PORT/app` (e.g.
`http://182.70.254.11:1010/nextcloud`), add the portal as another subpath on the
**same** web server. First find which one you run:

```bash
systemctl is-active nginx apache2
```

**Nginx** — add the `location` block from `deploy/nginx/portal-subpath.conf`
inside your existing `server { listen 1010; … }`, then:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Apache** — enable proxy modules and add the block from
`deploy/apache/portal-subpath.conf` inside your `<VirtualHost *:1010>`:
```bash
sudo a2enmod proxy proxy_http headers
sudo apachectl configtest && sudo systemctl reload apache2
```

Then browse to `http://182.70.254.11:1010/reverse-ssh/` and **change the
bootstrap admin password**.

The subpath, app port, and external URL are configurable when running setup:
```bash
sudo BASE_PATH=/reverse-ssh APP_PORT=8011 \
     PUBLIC_URL=http://182.70.254.11:1010/reverse-ssh \
     bash deploy/setup_vps.sh
```
These map to `PORTAL_BASE_PATH`, the uvicorn `--port`, and `PORTAL_PUBLIC_URL`.
`PUBLIC_URL` is what the portal puts into the device install commands, so it must
be the address devices can actually reach.

### Alternative: dedicated subdomain + TLS

For a clean `https://portal.example.com` instead of a subpath, leave
`PORTAL_BASE_PATH` empty and use `deploy/nginx/portal.conf` with a real cert:
```bash
sudo cp deploy/nginx/portal.conf /etc/nginx/sites-available/portal.conf
sudo ln -s /etc/nginx/sites-available/portal.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d portal.example.com
sudo systemctl reload nginx
```
(Plain HTTP over a subpath works, but TLS is strongly preferred. If you use a
self-signed cert, devices need `AGENT_INSECURE_TLS=1` — discouraged.)

### Key VPS prerequisites (handled by `setup_vps.sh`)
- A locked-down `tunnel` user; the portal runs as this user so it can rewrite
  `~/.ssh/authorized_keys`.
- `sshd`: `GatewayPorts clientspecified`, and a `Match User tunnel` block that
  permits only remote forwarding (no shell, no pty, `ForceCommand nologin`).
- Firewall: open `443` and the tunnel port range (default `20000-29999`).

## Device setup

From the device detail page, copy the generated command:

**Linux** (root):
```bash
curl -fsSL https://PORTAL/static/install.sh \
  | sudo PORTAL_URL=https://PORTAL ENROLL_TOKEN=xxxx bash
```

**Windows** (elevated PowerShell):
```powershell
$env:PORTAL_URL='https://PORTAL'; $env:ENROLL_TOKEN='xxxx'
irm $env:PORTAL_URL/static/install.ps1 | iex
```

Requirements: Python 3 and the OpenSSH `ssh` client on PATH. See `agent/README.md`.

## Local development

```bash
cd server
python -m venv venv && . venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000 and log in with `admin` / `admin` (the local
defaults from `app/config.py`). On a non-Linux dev box the `authorized_keys`
write is skipped gracefully and listener detection returns "unknown".

## Security notes

- **Public binding exposes device ports to the internet.** Anyone who can reach
  `VPS_IP:PORT` can reach the forwarded service, so rely on that service's own
  auth (SSH keys for shells). Disable/delete tunnels when not in use; consider
  firewalling the range down to only assigned ports.
- Device keys are `restrict`ed and limited via `permitlisten` to exactly their
  assigned ports — a device key cannot open any other port or get a shell.
- Enrollment tokens are single-use and expire (default 30 min).
- Serve the portal over TLS; keep `PORTAL_SECRET_KEY` and `.env` private.

## Configuration

All settings have `PORTAL_`-prefixed env vars (see `app/config.py`): `VPS_HOST`,
`VPS_SSH_PORT`, `TUNNEL_USER`, `PORT_RANGE_START/END`, `AUTHORIZED_KEYS_PATH`,
`SECRET_KEY`, `ENROLL_TOKEN_TTL`, `HEARTBEAT_ONLINE_WINDOW`, and the bootstrap
admin credentials.
