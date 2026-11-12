# Apple Logo Glow

If you upcycled an old MacBook with the glowing Apple logo into a Linux
server, this repo lets you use that logo again. Mine sits on a wall with the
lid shut, so the logo is all you ever see of the machine. You can run it
purely as a cool aesthetic, a slow glow pulsing away on a shelf, or turn it
into a status light that tells you what the server is doing. It's the
screen's backlight doing all the work, driven by a small Python script, so
you can tune every bit of it or write your own behaviour.

<!--
Hero image: save a photo or loop as assets/demo.gif, then uncomment:
![Only the Apple logo glows on the closed lid](assets/demo.gif)
-->

## Who this is for

Two requirements:

- An old MacBook with the glowing Apple logo: about 2006-2015 MacBook,
  MacBook Air or MacBook Pro.
- Linux installed on it.

After 2016 Apple switched to the plain metal logo that never lights up, and
macOS doesn't hand you the backlight anyway, so neither of those can do
this. What it does need is root, since it writes to sysfs and drives the
console, and it was written and tested on Ubuntu with the stock tty1 text
console (Debian and Ubuntu both default to it).

## Getting it running

```bash
git clone https://github.com/PietroContolini/apple-logo-glow.git
cd apple-logo-glow
sudo bash install.sh
```

There's nothing to install by hand first: on a reasonably stock Ubuntu or
Debian you already have everything it uses (systemd, python3, setterm). The
logo should start breathing within a second or two. `systemctl status glowd`
if you want to confirm it's running, `journalctl -u glowd` if something
looks wrong; the first few lines there also tell you which backlight device
it found and what range that device uses.

`install.sh` copies the files to `/opt/serverglow`, backs up and swaps the
lid handler, and enables the unit, so the glow comes back by itself after
every reboot. If you ever want it gone, `sudo bash revert.sh` puts the
machine back exactly like it was.

## Patterns and config

Three patterns come with it:

- `breathing`, the default: a slow inhale and exhale, Apple Watch style,
  one cycle every six seconds out of the box.
- `heartbeat`: a lub-dub pulse, if you prefer your servers to have a
  cardiovascular system. The same `period` knob sets the tempo.
- `load`: the status one. It reads CPU use from `/proc/stat` on every frame
  and smooths it over about half a second, so the glow reacts without
  flickering. Server idle, the logo does a slower and dimmer 12-second
  breath; CPU working, it climbs, hitting full brightness somewhere around
  45% sustained load.

All the settings are in `/opt/serverglow/glow.conf`:

```ini
mode = breathing    # breathing | heartbeat | load
min = 8             # dimmest level (0-100)
max = 100           # brightest level (0-100)
period = 6.0        # seconds per cycle, for breathing and heartbeat
open_level = 60     # brightness with the lid open, so the screen is readable
```

Edit it, then `sudo systemctl reload glowd` (that's a SIGHUP, the glow never
hiccups) or restart the service if you're feeling traditional. The file is
forgiving: numbers get clamped to sane ranges when they're loaded, and a
line it can't parse is logged and skipped, so a typo can't take the glow
down.

If none of the three patterns fit, writing your own is easy: the daemon is
about 300 lines of standard-library Python and a pattern is just a function
from elapsed seconds to a level of 0-100. Copy `heartbeat_level()`, add a
branch in `main()`, and if you want your own config knobs, add them to the
defaults dict in `load_cfg()` first (unknown keys in glow.conf are ignored
on purpose, which is also why a typo in there never breaks the daemon). If
you come up with a good one, send a PR.

## How it works

There's no logo LED in these lids. The panel's backlight shines through a
light-guide film, and the logo cut-out is the only place light escapes. So
if you keep the panel powered with a black console and drive the backlight
up and down, the logo glows and nothing else does.

```
glow.conf -> glowd -> /sys/class/backlight -> panel -> logo cut-out
```

What `install.sh` sets up:

- It backs up `/etc/acpi/lid.sh` and replaces it, so closing the lid no
  longer blanks the panel (opening it still behaves normally).
- It installs `glowd.service`, which runs `glow-prepare.sh` first: wakes the
  panel up, switches off the console auto-blanking at runtime, and turns
  kernel console messages down to level 3 so boot text doesn't glow through
  the lid.
- Then the daemon runs, writing brightness at 30 fps. Patterns are computed
  from real time instead of counting ticks, so they never drift, and it
  skips a write whenever the level hasn't changed. It also finds your
  backlight device itself (`acpi_video0` or `intel_backlight`) and scales to
  whatever range that device uses.

The lid sensor is checked ten times a second. Open it: the glow stops, the
screen parks at `open_level`, everything behaves like stock Linux. Close it:
the panel gets woken up and the pattern picks up where it left off. Every
few minutes it also re-pokes the console in case anything blanked it behind
its back.

A few choices I'd make again: standard library only, nothing to `pip
install` on a box that isn't your dev machine; config reloads over SIGHUP so
tuning doesn't restart anything; and if there's no backlight device at all
it logs why and exits, rather than running forever doing nothing.

## Good to know

- Machine changes, all undone by `sudo bash revert.sh`: the lid.sh swap
  above (original kept at `/etc/acpi/lid.sh.pre-glow`), tty1 auto-blank off
  at runtime only (kernel boot parameters untouched), console quieted.
  Stock behaviour again from the next reboot.
- It runs as root, because writing brightness and poking the console both
  need it. That's the whole footprint: one unit and those few system files.
- Power: the backlight adds roughly 1-4W depending on how bright you run
  it, and the machine runs a little warmer.
- Logo dark after a reboot? `journalctl -u glowd`, then check
  `cat /sys/class/backlight/*/brightness`. If that directory doesn't exist
  you're not on a laptop and this was never going to work.
- If it's going on a wall: leave the hinge gap clear and don't cover the
  rear vents. The aluminium body is doing the cooling.

## License

MIT. PRs, especially with new patterns, very welcome.
