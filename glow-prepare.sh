#!/bin/sh
# Runs before glowd at boot (harmless to re-run any time).
# - poke the panel awake now: a console blanked by consoleblank/lid.sh may be
#   in DPMS sleep, and the logo can only glow while the panel is powered
# - then disable per-VT auto-blanking on tty1: the kernel cmdline's
#   consoleblank=60 only sets the *initial* interval, so this turns it off at
#   runtime for tty1 without touching GRUB
# - keep routine kernel messages off the console so they don't light up text
#   through the panel; errors and warnings still get through
setterm --term linux --blank poke </dev/tty1 >/dev/tty1 2>/dev/null || true
setterm --term linux --blank 0 </dev/tty1 >/dev/tty1 2>/dev/null || true
dmesg --console-level 3 2>/dev/null || true
exit 0
