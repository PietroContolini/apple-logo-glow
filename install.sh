#!/bin/bash
# Install the Apple logo glow setup (run with sudo: bash install.sh).
# Fully undo later with: sudo bash revert.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="/opt/serverglow"

[ "$(id -u)" -eq 0 ] || { echo "run me with sudo: sudo bash install.sh"; exit 1; }

if ! ls /sys/class/backlight/*/brightness >/dev/null 2>&1; then
  echo "WARNING: no backlight device under /sys/class/backlight."
  echo "         This is meant for laptops (old glowing-logo MacBooks)."
fi

echo "==> installing files to $TARGET"
mkdir -p "$TARGET"
cp "$SRC/glowd.py" "$SRC/glow-prepare.sh" "$SRC/README.md" "$TARGET/"
[ -f "$TARGET/glow.conf" ] || cp "$SRC/glow.conf" "$TARGET/"   # keep user edits
chmod 755 "$TARGET/glow-prepare.sh"

echo "==> backing up /etc/acpi/lid.sh -> /etc/acpi/lid.sh.pre-glow"
[ -f /etc/acpi/lid.sh.pre-glow ] || cp /etc/acpi/lid.sh /etc/acpi/lid.sh.pre-glow

echo "==> replacing lid.sh: closing the lid no longer blanks the panel"
cat > /etc/acpi/lid.sh <<'EOF2'
#!/bin/bash
# glowd setup: lid close must NOT blank the panel (the glowing logo is lit
# by the panel backlight). Opening the lid still restores it.
STATE=$(awk '{print $2}' /proc/acpi/button/lid/*/state)
if [ "$STATE" != "closed" ]; then
  setterm --term linux --blank poke </dev/tty1 >/dev/tty1
fi
EOF2

echo "==> installing systemd unit glowd.service"
cp "$SRC/glowd.service" /etc/systemd/system/glowd.service
systemctl daemon-reload
systemctl enable --now glowd.service

echo "==> done - the lid logo should be glowing now."
systemctl --no-pager -l status glowd.service 2>/dev/null | head -n 12 || true
echo "   (full status: systemctl status glowd)"
