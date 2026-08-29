#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo ./install.sh" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=/opt/raspberry-pi-load
SERVICE_FILE=/etc/systemd/system/raspberry-pi-load.service

install -d -m 0755 "$INSTALL_DIR"
install -m 0755 "$SCRIPT_DIR/raspberry_pi_load.py" "$INSTALL_DIR/raspberry_pi_load.py"
install -m 0644 "$SCRIPT_DIR/raspberry-pi-load.service" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable --now raspberry-pi-load.service

echo "Installed and started raspberry-pi-load.service"
echo "Status: sudo systemctl status raspberry-pi-load.service"
echo "Logs:   journalctl -u raspberry-pi-load.service -f"
