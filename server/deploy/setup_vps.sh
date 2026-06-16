#!/usr/bin/env bash
# One-time VPS setup for the reverse-ssh tunnel portal.
# Run as root on the VPS (Debian/Ubuntu assumed; adjust for other distros).
set -euo pipefail

TUNNEL_USER="${TUNNEL_USER:-tunnel}"
PORT_START="${PORT_START:-20000}"
PORT_END="${PORT_END:-29999}"
# Install alongside your other sites under /var/www by default.
PORTAL_DIR="${PORTAL_DIR:-/var/www/reverse-ssh-portal}"
# Local port uvicorn listens on (proxied by your shared web server).
APP_PORT="${APP_PORT:-8011}"
# Python interpreter for the venv (needs >= 3.9; 3.8 lacks PEP 604/585 runtime
# type-hint support that FastAPI/Pydantic rely on).
PYTHON_BIN="${PYTHON_BIN:-python3}"
# Subpath the portal is served under, and its externally reachable URL.
BASE_PATH="${BASE_PATH:-/reverse-ssh}"
PUBLIC_URL="${PUBLIC_URL:-http://$(curl -fsS https://api.ipify.org || echo CHANGE_ME):1010${BASE_PATH}}"
REPO_SERVER_DIR="${REPO_SERVER_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

echo "==> Creating locked-down tunnel user '$TUNNEL_USER'"
if ! id "$TUNNEL_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /usr/sbin/nologin "$TUNNEL_USER"
fi
install -d -m 700 -o "$TUNNEL_USER" -g "$TUNNEL_USER" "/home/$TUNNEL_USER/.ssh"
touch "/home/$TUNNEL_USER/.ssh/authorized_keys"
chown "$TUNNEL_USER:$TUNNEL_USER" "/home/$TUNNEL_USER/.ssh/authorized_keys"
chmod 600 "/home/$TUNNEL_USER/.ssh/authorized_keys"

echo "==> Configuring sshd (GatewayPorts + tunnel-only Match block)"
SSHD_SNIPPET=/etc/ssh/sshd_config.d/reverse-ssh-portal.conf
cat > "$SSHD_SNIPPET" <<EOF
# Managed by reverse-ssh portal setup
GatewayPorts clientspecified
ClientAliveInterval 30
ClientAliveCountMax 3

Match User $TUNNEL_USER
    AllowTcpForwarding remote
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    ForceCommand /usr/sbin/nologin
EOF
sshd -t && systemctl reload ssh || systemctl reload sshd

echo "==> Opening firewall ports (ufw if present)"
if command -v ufw >/dev/null; then
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw allow "${PORT_START}:${PORT_END}/tcp" || true
fi

echo "==> Installing portal into $PORTAL_DIR"
mkdir -p "$PORTAL_DIR"
cp -r "$REPO_SERVER_DIR/app" "$REPO_SERVER_DIR/requirements.txt" "$PORTAL_DIR/"
echo "    Using interpreter: $("$PYTHON_BIN" --version 2>&1)"
"$PYTHON_BIN" -m venv "$PORTAL_DIR/venv"
"$PORTAL_DIR/venv/bin/pip" install --upgrade pip
"$PORTAL_DIR/venv/bin/pip" install -r "$PORTAL_DIR/requirements.txt"

echo "==> Writing $PORTAL_DIR/.env (edit secrets before going live!)"
if [ ! -f "$PORTAL_DIR/.env" ]; then
  cat > "$PORTAL_DIR/.env" <<EOF
PORTAL_VPS_HOST=$(curl -fsS https://api.ipify.org || echo CHANGE_ME)
PORTAL_VPS_SSH_PORT=2201
PORTAL_TUNNEL_USER=$TUNNEL_USER
PORTAL_PORT_RANGE_START=$PORT_START
PORTAL_PORT_RANGE_END=$PORT_END
PORTAL_AUTHORIZED_KEYS_PATH=/home/$TUNNEL_USER/.ssh/authorized_keys
PORTAL_BASE_PATH=$BASE_PATH
PORTAL_PUBLIC_URL=$PUBLIC_URL
PORTAL_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
PORTAL_BOOTSTRAP_ADMIN_USER=admin
PORTAL_BOOTSTRAP_ADMIN_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')
EOF
  echo "    Generated admin password is in $PORTAL_DIR/.env — log in and change it."
fi
chown -R "$TUNNEL_USER:$TUNNEL_USER" "$PORTAL_DIR"
chmod 600 "$PORTAL_DIR/.env"

echo "==> Installing systemd unit"
sed "s#__PORTAL_DIR__#$PORTAL_DIR#g; s#__USER__#$TUNNEL_USER#g; s#__PORT__#$APP_PORT#g" \
  "$REPO_SERVER_DIR/deploy/systemd/portal.service" > /etc/systemd/system/reverse-ssh-portal.service
systemctl daemon-reload
systemctl enable --now reverse-ssh-portal.service

echo
echo "Portal running on 127.0.0.1:$APP_PORT (as $TUNNEL_USER), under base path '$BASE_PATH'."
echo "Detect your shared web server:"
echo "    systemctl is-active nginx apache2 2>/dev/null"
echo "Then add the matching subpath proxy and reload:"
echo "  - nginx : deploy/nginx/portal-subpath.conf  (a 'location $BASE_PATH/' block in your :1010 server)"
echo "  - apache: deploy/apache/portal-subpath.conf  (a <Location $BASE_PATH/> proxy block)"
echo "Set APP_PORT in both to $APP_PORT. Then browse: $PUBLIC_URL"
