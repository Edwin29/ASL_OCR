#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo ./uninstall.sh" >&2
    exit 1
fi

systemctl disable --now raspberry-pi-load.service 2>/dev/null || true
rm -f /etc/systemd/system/raspberry-pi-load.service
rm -rf /opt/raspberry-pi-load
systemctl daemon-reload
echo "Uninstalled raspberry-pi-load.service"
