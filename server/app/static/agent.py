#!/usr/bin/env python3
"""Reverse SSH tunnel agent (cross-platform, standard-library only).

Two modes:

  enroll  --portal URL --token TOKEN [--config DIR]
      Registers with the portal, saving the device API key + private SSH key.

  run     [--config DIR]
      Polls the portal for the desired tunnel set and supervises one
      ``ssh -R`` process per tunnel, reconciling on every poll. Sends heartbeats.

Requires the OpenSSH ``ssh`` client on PATH. No third-party Python packages.
"""
import argparse
import json
import os
import platform
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_CONFIG_DIR = (
    os.environ.get("AGENT_CONFIG_DIR")
    or (r"C:\ProgramData\reverse-ssh-agent" if os.name == "nt" else "/etc/reverse-ssh-agent")
)


def config_paths(config_dir):
    return {
        "dir": config_dir,
        "config": os.path.join(config_dir, "config.json"),
        "key": os.path.join(config_dir, "id_ed25519"),
    }


def http_json(url, method="GET", data=None, bearer=None, timeout=20):
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    # Tolerate self-signed certs on the portal (common for a personal VPS).
    ctx = ssl.create_default_context()
    if os.environ.get("AGENT_INSECURE_TLS") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode())


# --------------------------------------------------------------------------- #
# enroll
# --------------------------------------------------------------------------- #
def cmd_enroll(args):
    paths = config_paths(args.config)
    os.makedirs(paths["dir"], exist_ok=True)

    payload = {
        "token": args.token,
        "hostname": socket.gethostname(),
        "os": "windows" if os.name == "nt" else platform.system().lower(),
    }
    url = args.portal.rstrip("/") + "/api/agent/enroll"
    try:
        result = http_json(url, method="POST", data=payload)
    except urllib.error.HTTPError as e:
        sys.exit(f"Enrollment failed ({e.code}): {e.read().decode(errors='ignore')}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach portal: {e}")

    # Write the private key (0600) and config.
    with open(paths["key"], "w", newline="\n") as f:
        f.write(result["private_key"])
    try:
        os.chmod(paths["key"], 0o600)
    except OSError:
        pass

    config = {
        "portal_url": args.portal.rstrip("/"),
        "api_key": result["api_key"],
        "device_name": result["device_name"],
        "vps_host": result["vps_host"],
        "vps_ssh_port": result["vps_ssh_port"],
        "tunnel_user": result["tunnel_user"],
        "poll_interval": result.get("poll_interval", 15),
        "key_path": paths["key"],
    }
    with open(paths["config"], "w") as f:
        json.dump(config, f, indent=2)
    try:
        os.chmod(paths["config"], 0o600)
    except OSError:
        pass
    print(f"Enrolled as '{result['device_name']}'. Config written to {paths['config']}")


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def load_config(config_dir):
    paths = config_paths(config_dir)
    if not os.path.exists(paths["config"]):
        sys.exit(f"No config at {paths['config']}. Run 'enroll' first.")
    with open(paths["config"]) as f:
        return json.load(f)


def ssh_command(cfg, spec):
    bind = spec.get("bind", "127.0.0.1")
    return [
        "ssh",
        "-N",
        "-T",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-i", cfg["key_path"],
        "-p", str(cfg["vps_ssh_port"]),
        "-R", f"{bind}:{spec['remote_port']}:{spec['local_host']}:{spec['local_port']}",
        f"{cfg['tunnel_user']}@{cfg['vps_host']}",
    ]


def reconcile(cfg, desired, running):
    """Start/stop ssh processes so ``running`` matches ``desired`` (by remote_port)."""
    desired_ports = {s["remote_port"]: s for s in desired}

    # Stop tunnels no longer desired, or dead processes.
    for port in list(running):
        proc = running[port]
        if port not in desired_ports or proc.poll() is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            del running[port]

    # Start tunnels that should be running but aren't.
    for port, spec in desired_ports.items():
        if port not in running:
            cmd = ssh_command(cfg, spec)
            print(f"[tunnel] open {cfg['vps_host']}:{port} -> "
                  f"{spec['local_host']}:{spec['local_port']}")
            running[port] = subprocess.Popen(cmd)


def cmd_run(args):
    cfg = load_config(args.config)
    state_url = cfg["portal_url"] + "/api/agent/state"
    hb_url = cfg["portal_url"] + "/api/agent/heartbeat"
    interval = max(5, int(cfg.get("poll_interval", 15)))
    running = {}

    print(f"Agent '{cfg['device_name']}' polling {cfg['portal_url']} every {interval}s")
    while True:
        try:
            state = http_json(state_url, bearer=cfg["api_key"])
            reconcile(cfg, state.get("tunnels", []), running)
            http_json(
                hb_url, method="POST",
                data={"active_ports": sorted(running)}, bearer=cfg["api_key"],
            )
        except urllib.error.HTTPError as e:
            print(f"[warn] portal returned {e.code}", file=sys.stderr)
        except (urllib.error.URLError, socket.timeout) as e:
            print(f"[warn] portal unreachable: {e}", file=sys.stderr)
        except Exception as e:  # keep the supervisor alive no matter what
            print(f"[warn] {e}", file=sys.stderr)
        time.sleep(interval)


def main():
    p = argparse.ArgumentParser(description="Reverse SSH tunnel agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("enroll")
    pe.add_argument("--portal", required=True, help="Portal base URL")
    pe.add_argument("--token", required=True, help="One-time enrollment token")
    pe.add_argument("--config", default=DEFAULT_CONFIG_DIR)
    pe.set_defaults(func=cmd_enroll)

    pr = sub.add_parser("run")
    pr.add_argument("--config", default=DEFAULT_CONFIG_DIR)
    pr.set_defaults(func=cmd_run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
