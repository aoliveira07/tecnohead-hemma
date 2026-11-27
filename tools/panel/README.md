# Tecnohead kitchen panel power schedule

`tecnohead-panel-power-schedule.service` is installed on panel `1.106` and
controls the X11/HDMI display, not the Home Assistant server:

- Sunday through Thursday: display awake from 05:00 through 20:59;
- Friday and Saturday: display awake from 05:00 through 21:59;
- outside those windows: the display is blanked and DPMS is allowed to turn it
  off;
- during the active window: DPMS and idle/sleep are disabled, so the EMA
  screensaver remains available without the computer suspending.

The computer itself is intentionally not forced into Linux suspend/hibernate.
That would prevent the existing daily reboot at 03:00 and would require a
hardware-specific RTC wake-up configuration. The existing kiosk reboot timer
remains at 03:00, two hours before the 05:00 display start.

For a deterministic schedule check without touching X11:

```sh
TECNOHEAD_PANEL_SCHEDULE_DAY=5 TECNOHEAD_PANEL_SCHEDULE_TIME=2159 \
  ./tecnohead-panel-power-schedule.sh --print-state
```
