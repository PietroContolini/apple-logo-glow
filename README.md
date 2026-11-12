# Apple logo glow

Turns the glowing Apple logo on the closed lid of an old MacBook into a
status light. The logo is lit by the LCD panel's own backlight (a light-guide
film in the lid assembly; the logo cut-out is the only place light escapes),
so this keeps the panel powered with a black screen and pulses the
backlight. From outside you just see the logo, glowing.

Handy for a wall-mounted or headless server: the logo becomes a slow
breathing status LED.

## Supported hardware

- Old MacBooks with the glowing logo: about 2006-2015 MacBook, MacBook Air
  and MacBook Pro.
- Linux installed on that machine. Written and tested on Ubuntu; it needs a
  Linux text console on tty1, which is the default on Debian and Ubuntu.
- Post-2016 MacBooks do not work: the logo no longer lights up.
- macOS does not work: there is no sysfs backlight access.

## Usage

    sudo bash install.sh              # set it all up in /opt/serverglow
    sudo systemctl restart glowd      # after editing /opt/serverglow/glow.conf
    sudo bash revert.sh               # fully undo

Patterns and levels: see the Customizing section below. While the lid is
open the pulse pauses and the screen parks at `open_level` (default 60),
giving full stock console behaviour; closing the lid resumes the pattern.

## Customizing

All settings live in `/opt/serverglow/glow.conf`. Edit it, then apply with
either:

    sudo systemctl reload glowd     # SIGHUP, no interruption
    sudo systemctl restart glowd    # or a full restart

Every option, with the shipped defaults:

    # Pattern: breathing | heartbeat | load
    mode = breathing

    # Backlight levels, 0-100. 100 is full backlight.
    min = 8
    max = 100

    # Seconds per cycle, for breathing and heartbeat.
    period = 6.0

    # Fixed backlight while the lid is open (maintenance), so the
    # console stays readable.
    open_level = 60

The three patterns:

- `breathing` (default): a slow Apple-Watch style inhale and exhale, one
  cycle every `period` seconds.
- `heartbeat`: a lub-dub pulse, one double beat every `period` seconds.
- `load`: a CPU usage indicator. An idle machine breathes slowly and
  faintly; the busier the CPU gets the brighter the logo, reaching `max`
  at roughly 45% sustained load.

Tuning tips:

- `min = 8, max = 100` is the full-on look; drop `max` to around 45 for a
  subtler glow in a dark room.
- `period` only affects `breathing` and `heartbeat`; `load` uses its own
  slow idle breath and then follows CPU use.
- Raise `min` if you want the logo never to settle dimly, or lower it for
  deeper contrast between pulses.

## Files

- `glowd.py`        the daemon: reads glow.conf, drives the backlight at 30 fps
- `glow.conf`       pattern and level config
- `glow-prepare.sh` runs at boot before glowd: stops tty1 auto-blank and keeps
                    routine kernel messages off the console
- `glowd.service`   systemd unit (installed to /etc/systemd/system/)
- `install.sh`      copies the files to /opt/serverglow, backs up and replaces
                    /etc/acpi/lid.sh, installs the unit
- `revert.sh`       undoes everything install.sh changed

## Machine changes

- `/etc/acpi/lid.sh` is backed up to `/etc/acpi/lid.sh.pre-glow` and replaced,
  so closing the lid no longer blanks the panel (opening it still restores
  the console).
- tty1 auto-blank is disabled at runtime only; the kernel's `consoleblank=`
  boot parameter is untouched, so removing glowd restores the old behaviour.
- Kernel console messages are reduced to level 3, so console text does not
  glow through the panel.
- The service runs as root, because writing sysfs brightness and poking tty1
  both require it.

## Notes

- Power cost of the panel backlight: roughly 1-4 W continuous depending on
  the level; the machine also runs slightly warmer.
- Both backlight styles are handled: glowd picks a device at start-up
  (preferring `acpi_video0`, falling back to whatever exists) and scales
  levels by that device's `max_brightness`.
- If the logo stays dark after a reboot, check `journalctl -u glowd` and
  `cat /sys/class/backlight/*/brightness`.
- Wall mount: leave the hinge/vent gap free, the aluminium lid and body do
  the dissipating. Do not flush-mount over the rear vents.

## License

MIT, see `LICENSE`.
