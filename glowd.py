#!/usr/bin/env python3
"""
glowd - makes the glowing Apple logo pulse on the closed lid of an old MacBook.

The glowing logo is lit by the LCD panel's own backlight (a light-guide film
in the lid assembly; the logo cut-out is the only place light escapes), so
driving /sys/class/backlight while the screen stays black turns the lid into
a status indicator. No separate logo LED exists; this is the only way.

Lid-aware:
- lid closed  -> "server mode": patterns run on the backlight
- lid open    -> "maintenance": pattern pauses, brightness is parked at
                 open_level, and the console behaves stock (60s idle blank)
- lid closes  -> panel is poked awake (in case consoleblank put it to sleep)
                 and the pattern resumes

The loop runs at 30 fps with absolute-deadline pacing (no drift), skipping
writes when the integer level is unchanged. Patterns are computed from wall
time, never from tick counts, so the rate only affects smoothness.

Config lives in glow.conf next to this file. Send SIGHUP to reload it,
or just run: sudo systemctl restart glowd
"""

import glob
import math
import os
import signal
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
CONF_PATH = os.path.join(BASE, "glow.conf")

BACKLIGHT_DIR = "/sys/class/backlight"
LID_GLOB = "/proc/acpi/button/lid/*/state"
TICK_S = 1.0 / 30.0   # 30 fps target frame time
LID_POLL_S = 0.1      # lid state is checked at 10 Hz (cheaper than 30)
REARM_S = 240.0       # re-assert "no console blanking" every 4 minutes
EMA_TAU_S = 0.45      # load-mode smoothing time constant, in SECONDS
running = True
_reload = False
last_write = -1
bright_path = None   # set in main() by find_backlight()
bright_max = 100     # device scale: writes level * bright_max / 100


def log(msg):
    sys.stdout.write(f"glowd: {msg}\n")
    sys.stdout.flush()


def load_cfg():
    cfg = {
        "mode": "breathing",   # breathing | heartbeat | load
        "min": 8,              # lowest backlight level (subtle glow)
        "max": 100,            # peak backlight level
        "period": 6.0,         # seconds per breathing cycle
        "open_level": 60,      # backlight while the lid is open (readable)
        "step": 4,             # quantize output to whole steps of this many
                               # levels (1 = finest / old behaviour)
    }
    if os.path.exists(CONF_PATH):
        for raw in open(CONF_PATH, encoding="utf-8"):
            line = raw.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            key, val = (p.strip() for p in line.split("=", 1))
            if key not in cfg:
                continue
            try:
                if key == "mode":
                    cfg[key] = val.lower()
                elif key == "period":
                    cfg[key] = float(val)
                else:
                    cfg[key] = int(val)
            except ValueError:
                log(f"bad value for {key!r}: {val!r}, keeping default")
    cfg["min"] = max(0, min(cfg["min"], 100))
    cfg["max"] = max(cfg["min"] + 1, min(cfg["max"], 100))
    cfg["open_level"] = max(cfg["min"] + 1, min(cfg["open_level"], 100))
    cfg["step"] = max(1, min(cfg["step"], 50))
    return cfg


def find_backlight():
    """Pick a backlight device and its scale.

    Old MacBooks expose either acpi_video0 (native levels 0-100) or
    intel_backlight (raw levels up to max_brightness), depending on the
    kernel's acpi_backlight= setting. So: prefer acpi_video0, else take the
    first device found, and scale all 0-100 levels by max_brightness either
    way. Returns (brightness_path, max_brightness), or (None, 100) when there
    is no backlight at all (not a laptop, or no driver loaded).
    """
    try:
        devs = sorted(os.listdir(BACKLIGHT_DIR))
    except OSError:
        devs = []
    if not devs:
        return None, 100
    name = "acpi_video0" if "acpi_video0" in devs else devs[0]
    max_b = 100
    try:
        with open(os.path.join(BACKLIGHT_DIR, name, "max_brightness"),
                  encoding="ascii") as f:
            max_b = max(1, int(f.read().strip()))
    except (OSError, ValueError):
        pass
    return os.path.join(BACKLIGHT_DIR, name, "brightness"), max_b


def read_lid():
    """Return 'open' or 'closed' from /proc/acpi, or None if unreadable."""
    for path in glob.glob(LID_GLOB):
        try:
            with open(path, encoding="ascii") as f:
                parts = f.read().split()
            state = parts[-1].lower() if parts else ""
            if state in ("open", "closed"):
                return state
        except OSError:
            pass
    return None


def read_cpu():
    with open("/proc/stat", encoding="ascii") as f:
        parts = f.readline().split()
    vals = [int(x) for x in parts[1:8]]  # user nice system idle iowait irq softirq
    idle = vals[3] + vals[4]
    return idle, sum(vals)


def smoothstep(v):
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


def heartbeat_level(phase):
    """Lub-dub envelope for phase in [0, 1)."""
    segs = (
        (0.00, 0.10, 0.05, 1.00),   # first thump up
        (0.10, 0.24, 1.00, 0.12),   # down
        (0.30, 0.40, 0.12, 0.80),   # second thump up
        (0.40, 0.58, 0.80, 0.10),   # down
    )
    for a, b, v0, v1 in segs:
        if a <= phase < b:
            return v0 + (v1 - v0) * smoothstep((phase - a) / (b - a))
    return 0.10 + 0.12 * smoothstep((phase - 0.58) / 0.42)  # slow rise to next beat


def set_brightness(level):
    """Write a 0-100 backlight level; True on success. Skips if unchanged."""
    global last_write
    if level == last_write:
        return True
    try:
        with open(bright_path, "w", encoding="ascii") as f:
            f.write(str(int(round(level * bright_max / 100))))
        last_write = level
        return True
    except (OSError, TypeError, ValueError) as e:
        log(f"brightness write failed: {e}")
        return False


def rearm_console():
    """Poke the panel awake if blanked, and keep tty1 auto-blank off."""
    try:
        tty = open("/dev/tty1", "r")
        null = open(os.devnull, "w")
        subprocess.run(
            ["setterm", "--term", "linux", "--blank", "poke"],
            stdin=tty, stdout=null, stderr=null, check=True,
        )
        subprocess.run(
            ["setterm", "--term", "linux", "--blank", "0"],
            stdin=tty, stdout=null, stderr=null, check=True,
        )
        tty.close()
        null.close()
    except Exception as e:  # pragma: no cover
        log(f"console re-arm failed: {e}")


def main():
    global running, _reload, bright_path, bright_max

    def stop(*_):
        globals().__setitem__("running", False)

    def reload_(*_):
        globals().__setitem__("_reload", True)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGHUP, reload_)

    bright_path, bright_max = find_backlight()
    if bright_path is None:
        log("no backlight device under /sys/class/backlight - this is "
            "meant for laptops (old glowing-logo MacBooks)")
        sys.exit(1)
    log(f"backlight: {bright_path} (device scale 0-{bright_max})")

    cfg = load_cfg()
    lo, hi, period = cfg["min"], cfg["max"], cfg["period"]
    log(f"mode={cfg['mode']} min={lo} max={hi} period={period}s "
        f"open_level={cfg['open_level']} fps={1.0 / TICK_S:.0f}")

    start = time.monotonic()
    next_rearm = 0.0
    next_frame = time.monotonic()
    next_lid_check = 0.0
    ema_alpha = 1.0 - math.exp(-TICK_S / EMA_TAU_S)  # rate-independent smoothing
    last_idle, last_total = read_cpu(), None
    ema = 0.0

    lid = read_lid()
    open_mode = lid == "open"
    if lid is None:
        log("lid state unreadable, assuming closed (server mode)")
    elif open_mode:
        log("lid open at start: maintenance mode (pattern paused)")
        set_brightness(cfg["open_level"])
    else:
        log("lid closed: server mode, pattern active")

    while running:
        if _reload:
            _reload = False
            cfg = load_cfg()
            lo, hi, period = cfg["min"], cfg["max"], cfg["period"]
            start = time.monotonic()
            log(f"reloaded: mode={cfg['mode']} min={lo} max={hi} period={period}s "
                f"open_level={cfg['open_level']}")
            if open_mode:
                set_brightness(cfg["open_level"])

        now = time.monotonic()
        elapsed = now - start

        # --- lid state (cheap /proc read, polled at LID_POLL_S) -------------
        if now >= next_lid_check:
            next_lid_check = now + LID_POLL_S
            lid = read_lid()
            if lid in ("open", "closed") and (lid == "open") != open_mode:
                open_mode = lid == "open"
                if open_mode:
                    log("lid open: pulsing paused, "
                        f"screen parked at open_level={cfg['open_level']}")
                    set_brightness(cfg["open_level"])
                else:
                    log(f"lid closed: waking panel, resuming pattern ({cfg['mode']})")
                    rearm_console()
                    next_rearm = now + REARM_S

        if not open_mode:
            # --- server mode: pattern + blanking guard ----------------------
            if cfg["mode"] == "breathing":
                f = 0.5 - 0.5 * math.cos(2 * math.pi * (elapsed % period) / period)
                target = lo + (hi - lo) * f
            elif cfg["mode"] == "heartbeat":
                p = (elapsed % period) / period
                target = lo + (hi - lo) * heartbeat_level(p)
            else:  # load: idle -> slow faint breath, busy -> brighter (CPU meter)
                idle, total = read_cpu()
                if last_total is not None and total > last_total:
                    busy = 1.0 - min(1.0, (idle - last_idle) / (total - last_total))
                    ema += ema_alpha * (busy - ema)
                last_idle, last_total = idle, total
                if ema < 0.05:
                    f = 0.5 - 0.5 * math.cos(2 * math.pi * (elapsed % 12.0) / 12.0)
                    target = lo + (hi - lo) * (0.35 * f)
                else:
                    target = lo + (hi - lo) * min(1.0, ema * 2.2)

            level = int(round(max(0, min(100, target))))
            q = cfg.get("step", 1)
            if q > 1:
                # Snap to multiples of `step` above the pattern floor, so the
                # endpoints are always hit exactly. Every whole level that
                # reaches the hardware costs an ACPI interrupt plus a kernel
                # uevent that udev, PID 1 and logind all process (measured at
                # ~1.3% of a core per change-per-second on old MacBooks), so
                # fewer, bigger steps keep the glow looking identical on a
                # slow breath while cutting the CPU churn by the same factor.
                level = lo + int(round((level - lo) / q)) * q
            set_brightness(max(lo, min(100, level)))

            if now >= next_rearm:
                rearm_console()
                next_rearm = now + REARM_S

        # --- 30 fps frame pacing on absolute deadlines (no drift) -----------
        next_frame += TICK_S
        delay = next_frame - time.monotonic()
        if delay <= -0.5:          # fell far behind (long stall); resync
            next_frame = time.monotonic()
        elif delay > 0:
            time.sleep(delay)

    log("stopped")


if __name__ == "__main__":
    main()
