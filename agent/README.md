# Device agent

The canonical agent and installers are served by the portal so devices can fetch
them during enrollment. They live in the server's static directory:

- `server/app/static/agent.py` — the cross-platform agent (stdlib only)
- `server/app/static/install.sh` — Linux installer (creates a systemd service)
- `server/app/static/install.ps1` — Windows installer (creates a scheduled task)

## What the agent does

1. **enroll** — exchanges a one-time token for a per-device SSH private key + a
   long-lived API key, saved under `/etc/reverse-ssh-agent` (Linux) or
   `C:\ProgramData\reverse-ssh-agent` (Windows).
2. **run** — every ~15s, polls `GET /api/agent/state`, and supervises one
   `ssh -R` process per assigned tunnel (starting, stopping, and restarting them
   to match the portal). Sends a heartbeat each cycle.

Requirements on the device: Python 3 and the OpenSSH `ssh` client on PATH.

## Manual use (without the installer)

```bash
python3 agent.py enroll --portal https://portal.example --token <TOKEN>
python3 agent.py run
```
