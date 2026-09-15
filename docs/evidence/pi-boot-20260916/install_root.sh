#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
base=/home/user/ASL_OCR_PI/runtime/boot-setup-20260916
test ! -e /etc/systemd/system/asl-rfcomm.service
# Install privileged helper root-owned, so later user edits cannot change it.
install -d -m 755 /usr/local/lib/asl-demo
install -o root -g root -m 755 "$base/bind_rfcomm.sh" /usr/local/lib/asl-demo/bind_rfcomm.sh
sed 's|/home/user/ASL_OCR_PI/runtime/boot-setup-20260916/bind_rfcomm.sh|/usr/local/lib/asl-demo/bind_rfcomm.sh|' "$base/asl-rfcomm.service" > /etc/systemd/system/asl-rfcomm.service
chmod 644 /etc/systemd/system/asl-rfcomm.service
systemctl daemon-reload
systemctl enable --now asl-rfcomm.service
systemctl is-active asl-rfcomm.service
