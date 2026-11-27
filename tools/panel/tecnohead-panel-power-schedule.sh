#!/bin/sh
set -eu

# The kitchen panel must remain visible with Hemma's screensaver during the
# home's active hours, but should save the monitor outside those hours. This
# controls the X11 display power state; it deliberately does not suspend the
# whole computer, so the existing 03:00 reboot and the 05:00 wake-up remain
# reliable.

DISPLAY_NAME=${DISPLAY:-:0}
XAUTHORITY_FILE=${XAUTHORITY:-/home/tecnohead/.Xauthority}
POLL_SECONDS=${TECNOHEAD_PANEL_POWER_POLL_SECONDS:-30}

schedule_day() {
  printf '%s' "${TECNOHEAD_PANEL_SCHEDULE_DAY:-$(date +%u)}"
}

schedule_time() {
  printf '%s' "${TECNOHEAD_PANEL_SCHEDULE_TIME:-$(date +%H%M)}"
}

sleep_at() {
  case "$(schedule_day)" in
    1|2|3|4|7) printf '%s' 2100 ;; # Monday-Thursday and Sunday
    5|6)       printf '%s' 2200 ;; # Friday and Saturday
    *)         printf '%s' 2100 ;;
  esac
}

schedule_state() {
  now=$(schedule_time)
  end=$(sleep_at)
  if [ "$now" -ge 0500 ] && [ "$now" -lt "$end" ]; then
    printf '%s' active
  else
    printf '%s' sleep
  fi
}

print_schedule_state() {
  state=$(schedule_state)
  printf 'state=%s day=%s time=%s active=05:00-%s\n' \
    "$state" "$(schedule_day)" "$(schedule_time)" \
    "$(sleep_at | sed 's/\(..\)$/:\1/')"
}

if [ "${1:-}" = "--print-state" ]; then
  print_schedule_state
  exit 0
fi

xset_cmd() {
  DISPLAY="$DISPLAY_NAME" XAUTHORITY="$XAUTHORITY_FILE" xset "$@"
}

display_ready() {
  xset_cmd q >/dev/null 2>&1
}

set_active_display() {
  # Keep the HDMI panel lit while Hemma owns the visible screensaver.
  xset_cmd s off
  xset_cmd s noblank
  xset_cmd -dpms
}

set_sleep_display() {
  # Let X11 blank the display after a short grace period while leaving the
  # kiosk browser and Home Assistant running in the background.
  xset_cmd s 600 600
  xset_cmd s blank
  xset_cmd +dpms
  xset_cmd dpms 0 0 600
}

force_display_on() {
  xset_cmd dpms force on
}

force_display_off() {
  xset_cmd dpms force off
}

INHIBITOR_PID=

start_sleep_inhibitor() {
  if [ -n "$INHIBITOR_PID" ] && kill -0 "$INHIBITOR_PID" 2>/dev/null; then
    return 0
  fi

  INHIBITOR_PID=
  if command -v systemd-inhibit >/dev/null 2>&1; then
    systemd-inhibit \
      --what=idle:sleep \
      --who="Tecnohead kitchen panel" \
      --why="Keep the EMA screensaver visible during panel hours" \
      --mode=block \
      sleep infinity >/dev/null 2>&1 &
    INHIBITOR_PID=$!
    # A non-privileged session may be denied by logind. Do not leave a stale
    # PID that makes the schedule look protected when it is not.
    sleep 1
    if ! kill -0 "$INHIBITOR_PID" 2>/dev/null; then
      INHIBITOR_PID=
      printf '%s\n' "Warning: systemd sleep inhibitor could not be registered"
    fi
  fi
}

stop_sleep_inhibitor() {
  if [ -n "$INHIBITOR_PID" ]; then
    kill "$INHIBITOR_PID" 2>/dev/null || true
    INHIBITOR_PID=
  fi
}

cleanup() {
  stop_sleep_inhibitor
}

trap cleanup EXIT INT TERM HUP

# X11 can come up a little after the system service. Wait for it rather than
# failing once and leaving the panel with whatever power state it inherited.
while ! display_ready; do
  sleep 5
done

last_state=
while :; do
  state=$(schedule_state)

  if [ "$state" = active ]; then
    set_active_display
    start_sleep_inhibitor
    if [ "$last_state" != active ]; then
      force_display_on
      printf '%s\n' "Active window: 05:00-$(sleep_at | sed 's/\(..\)$/:\1/'); display on; sleep inhibited"
    fi
  else
    set_sleep_display
    stop_sleep_inhibitor
    if [ "$last_state" != sleep ]; then
      force_display_off
      printf '%s\n' "Outside active window: display sleep enabled until 05:00; system remains available for 03:00 reboot"
    fi
  fi

  last_state=$state
  sleep "$POLL_SECONDS"
done
