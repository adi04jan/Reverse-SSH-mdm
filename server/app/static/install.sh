#!/usr/bin/env bash
# Linux installer for the reverse-ssh tunnel agent.
#
# Usage (run as root):
#   curl -fsSL https://PORTAL/static/install.sh \
#     | sudo PORTAL_URL=https://PORTAL ENROLL_TOKEN=xxxx bash
set -euo pipefail

PORTAL_URL="${PORTAL_URL:?set PORTAL_URL}"
ENROLL_TOKEN="${ENROLL_TOKEN:?set ENROLL_TOKEN}"
INSTALL_DIR="/opt/reverse-ssh-agent"
CONFIG_DIR="/etc/reverse-ssh-agent"
SERVICE="reverse-ssh-agent"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v ssh >/dev/null || { echo "openssh client (ssh) is required"; exit 1; }

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
echo "Downloading agent..."
curl -fsSL "${PORTAL_URL%/}/static/agent.py" -o "$INSTALL_DIR/agent.py"
chmod 0755 "$INSTALL_DIR/agent.py"

echo "Enrolling with portal..."
python3 "$INSTALL_DIR/agent.py" enroll \
  --portal "$PORTAL_URL" --token "$ENROLL_TOKEN" --config "$CONFIG_DIR"

echo "Installing systemd service..."
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Reverse SSH Tunnel Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/agent.py run --config ${CONFIG_DIR}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}.service"
echo "Done. Check status with: systemctl status ${SERVICE}"
