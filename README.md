# Apple Logo Glow

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey)

**Turn an upcycled old MacBook into a home server you can see breathing
across the room.**

The glowing Apple logo is a ready-made status light hiding in plain sight.
This keeps the LCD panel powered behind a black screen and pulses its
backlight, so from the outside the only thing you see is the logo, glowing
through the cut-out. Run it as pure ambience, or as a live indicator of what
your server is actually doing. The three shipped patterns are defaults, not
a ceiling: everything is tunable from one config file, and a new pattern is
about fifteen lines of Python.

<!--
HERO SLOT: drop a photo or short loop at assets/demo.gif (or .jpg / .png),
then uncomment the line below:
![Only the Apple logo glows on a closed MacBook lid](assets/demo.gif)
-->

## Is this for you?

| Situation | Verdict |
|---|---|
| 2006-2015 MacBook / Air / Pro with the **glowing** logo, running Linux | Made for this |
| Lid shut on a shelf or wall | Ideal: closed lid becomes the status light |
| Lid open on a desk | Works; pulse pauses, console stays readable |
| Post-2016 MacBook | The logo no longer lights up, nothing to glow |
| macOS | Not possible: no sysfs backlight access |
| Desktop or non-laptop Linux box | Out of scope by design: no backlight, glowd logs why and exits |

Tested on a 2013 MacBook Air running Ubuntu with the stock tty1 text console
(the Debian/Ubuntu default). Needs root, since it writes sysfs and drives the
console.

## Quick start

```bash
git clone https://github.com/PietroContolini/apple-logo-glow.git
cd apple-logo-glow
sudo bash install.sh
```

Done. Files land in `/opt/serverglow`, the systemd unit starts glowd, and the
logo starts breathing. Verify with `systemctl status glowd`; logs live in
`journalctl -u glowd`.

Undo everything:

```bash
sudo bash revert.sh
```

That restores the original lid handler, removes the unit and
`/opt/serverglow`, and parks the panel: stock behaviour again from the next
reboot.

## Day to day

- **Tune it**: edit `/opt/serverglow/glow.conf`, then
  `sudo systemctl reload glowd` (SIGHUP, zero interruption) or
  `sudo systemctl restart glowd`.
- **Lid-aware**: lid closed is server mode, pattern running. Lid open is
  maintenance mode: pattern pauses, the screen parks at `open_level`, and
  stock idle-blanking works. Closing it again wakes the panel and resumes.

## Patterns

| Mode | What it looks like | Reach for it when |
|---|---|---|
| `breathing` (default) | slow Apple-Watch style inhale and exhale | you want calm |
| `heartbeat` | lub-dub double beat every cycle | you want a pulse you can count from the next room |
| `load` | idle: faint slow breath; busy: brighter | you want a CPU meter (hits `max` at roughly 45% sustained load) |

### Beyond the shipped three

A pattern is a function from elapsed seconds to a level between 0 and 100,
and `glowd.py` is around 300 lines of dependency-free Python. Add a mode in
the shape of `heartbeat_level()`, branch on it in `main()`, and any key you
define in `glow.conf` comes through for free. Disk space, load average,
service up or down, a rainbow cycle: same seam, no plumbing. PRs with new
patterns are very welcome.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `mode` | `breathing` | `breathing`, `heartbeat`, `load`, or your own |
| `min` | `8` | lowest backlight level (0-100), the glow floor |
| `max` | `100` | highest backlight level (0-100) |
| `period` | `6.0` | seconds per cycle (`breathing`, `heartbeat`) |
| `open_level` | `60` | fixed level while the lid is open, keep it readable |

```ini
mode = breathing
min = 8
max = 100
period = 6.0
open_level = 60
```

Values are clamped to sane ranges at load, and malformed lines are logged
and skipped. The config is meant to be hand-edited without fear.

## How it works

No magic and no reverse-engineered drivers: one physical fact plus one sysfs
file.

1. **The fact.** On these MacBooks the logo is lit by the LCD panel's own
   backlight through a light-guide film. There is no separate logo LED. The
   cut-out in the aluminium is the only place light escapes, which is why a
   black screen with a pulsing backlight reads as "glowing logo".
2. **Keep the panel alive.** At boot, `glow-prepare.sh` wakes the panel,
   switches off tty1 auto-blanking at runtime (the kernel's `consoleblank=`
   parameter is never touched), and drops kernel console messages to level 3
   so text does not glow through.
3. **Drive the backlight.** `glowd.py` runs a 30 fps loop paced on absolute
   deadlines, so it never drifts, and patterns are computed from wall-clock
   time, so frame rate only affects smoothness. Writes are skipped when the
   integer level has not changed. The backlight device is auto-detected
   (`acpi_video0` or `intel_backlight`) and levels are scaled by that
   device's `max_brightness`.
4. **Respect the lid.** `/proc/acpi/button/lid` is polled at 10 Hz. Open:
   pause, park, behave stock. Close: wake the panel, resume the pattern.

```
glow.conf ──SIGHUP──> glowd.py ──30 fps──> /sys/class/backlight ──> panel
  (tune by hand)       (Python 3, stdlib                          │
                        only, ~300 lines)                  light-guide film
                                                                │
                                                     only the logo cut-out
                                                          emits light
```

## Layout

    glowd.py         daemon: pattern loop, lid handling, config reload
    glow.conf        every tunable, hand-editable
    glow-prepare.sh  runs before glowd at boot: panel awake, quiet console
    glowd.service    unit: prepare, then python, restart on failure
    install.sh       copies files to /opt, backs up and swaps lid.sh,
                     installs and enables the unit
    revert.sh        undoes install.sh exactly

## What it changes on your machine

Full disclosure, all of it reversible with one command:

- `/etc/acpi/lid.sh` is backed up to `/etc/acpi/lid.sh.pre-glow` and
  replaced, so closing the lid no longer blanks the panel (opening it still
  restores the console).
- tty1 auto-blank disabled at runtime only; the `consoleblank=` boot
  parameter is untouched, so uninstalling glowd restores stock behaviour.
- Console verbosity lowered to level 3.
- One systemd unit, running as root.

`sudo bash revert.sh` reverses every line above.

## Design notes

- **Appliance, not project**: Python standard library only. Nothing to
  `pip install`, no virtualenv on a box whose job is not being a dev machine.
- **Timing**: absolute-deadline pacing plus wall-clock pattern math means the
  loop never drifts, and a config reload never knocks a cycle out of phase.
- **Reload beats restart**: config is swapped on SIGHUP, so tuning the glow
  never interrupts the glow.
- **Honest failure**: no backlight device (a desktop, say) is a clear log
  line and a non-zero exit, surfaced by systemd, rather than a daemon
  pretending to work.

## Troubleshooting

- **Logo dark after a reboot**: `journalctl -u glowd`, then
  `cat /sys/class/backlight/*/brightness` and the same path for `bl_power`.
- **Kernel text bleeding through the logo**: `dmesg --console-level 3`.
  `glow-prepare.sh` does this at every boot; run it manually after anything
  unusual.
- **No `/sys/class/backlight`**: laptop-only by design, see the table above.

## Power and mounting

- The panel backlight costs roughly 1-4 W continuously depending on level,
  and the machine runs slightly warmer.
- Wall mounting: leave the hinge/vent gap free. The aluminium lid and body
  do the dissipating; do not flush-mount over the rear vents.

## License

MIT. Issues and PRs welcome, especially new patterns.
