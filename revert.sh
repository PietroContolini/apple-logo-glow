#!/bin/bash
# Undo everything install.sh did (run with sudo: bash revert.sh)
set -euo pipefail
TARGET="/opt/serverglow"

[ "$(id -u)" -eq 0 ] || { echo "run me with sudo: sudo bash revert.sh"; exit 1; }

systemctl disable --now glowd.service 2>/dev/null || true
rm -f /etc/systemd/system/glowd.service
if [ -f /etc/acpi/lid.sh.pre-glow ]; then
  cp /etc/acpi/lid.sh.pre-glow /etc/acpi/lid.sh
  echo "==> original lid.sh restored"
fi
systemctl daemon-reload
rm -rf "$TARGET"
echo "==> removed $TARGET"
# park the panel in its old "off" state immediately
setterm --term linux --blank force </dev/tty1 >/dev/tty1 2>/dev/null || true
echo "==> original behaviour restored (identical again from the next reboot on)"
