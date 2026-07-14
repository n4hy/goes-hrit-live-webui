#!/usr/bin/env bash
#
# OnOff.sh - turn the entire GOES HRIT real-time system on or off.
#
# NOTE: `goes_run` (same directory) is the front door and the documented way in:
#   goes_run on|off [y|n]   where y = permanent (boot too), n = this boot only.
# It maps onto the verbs below. This script holds the unit logic; use it directly
# when you want a specific verb. Keep the logic here, not in goes_run.
#
# The pipeline is:
#   satdump-goes19.service   RF ingest / HRIT decode (SatDump)
#   goes-sse.service         SSE server + web APIs
#   goes-scheduler.service   predictive publisher + false-color composites
#   + maintenance/self-healing timers (publisher, cleanups, RTL-SDR check, watchdog)
#   + nginx (web frontend on :8080)
#
# Usage:
#   sudo ./OnOff.sh on        Start the whole pipeline now      (goes_run on n)
#   sudo ./OnOff.sh off       Stop the whole pipeline now       (goes_run off n)
#   sudo ./OnOff.sh restart   Stop then start
#   sudo ./OnOff.sh status    Show enabled/active state of every unit
#   sudo ./OnOff.sh enable    Start now AND enable at boot      (goes_run on y)
#   sudo ./OnOff.sh disable   Stop now AND disable at boot      (goes_run off y)
#
# The stack is DISABLED at boot as of 2026-07-14, deliberately (see README):
# the per-frame make_false_color.py worker holds a full core and wrecks any
# benchmark running beside it on this 4-core Pi. `on`/`off` do not change that;
# only `enable`/`disable` do.
#
set -euo pipefail

# Long-running services, listed in START order (stop order is the reverse).
# goes-scheduler Wants=goes-sse, so sse must be up before the scheduler.
SERVICES=(
  satdump-goes19.service
  goes-sse.service
  goes-scheduler.service
)

# Timers (order-independent). The watchdog timer is listed last so that on
# start-up it comes up after the services it monitors, and on shutdown it is
# stopped first (see stop_all) so it cannot restart SatDump mid-teardown.
TIMERS=(
  update-goes-fd-web.timer
  cleanup-bad-frames.timer
  satdump-cleanup.timer
  check-rtlsdr.timer
  goes-web-watchdog.timer
)

# nginx is shared web infrastructure: we ensure it is up on "on", but do NOT
# stop it on "off" (that would take down the web server and lock you out).
WEB_SERVICE="nginx"

# ---- helpers ---------------------------------------------------------------

# Re-exec as root if needed.
if [ "$(id -u)" -ne 0 ]; then
  exec sudo -- "$0" "$@"
fi

have_unit() { systemctl cat "$1" >/dev/null 2>&1; }

do_action() {  # do_action <verb> <unit>
  local verb="$1" unit="$2"
  if ! have_unit "$unit"; then
    printf '  %-28s %s\n' "$unit" "MISSING (skipped)"
    return 0
  fi
  if systemctl "$verb" "$unit" 2>/dev/null; then
    printf '  %-28s %s -> %s\n' "$unit" "$verb" "$(systemctl is-active "$unit" 2>/dev/null)"
  else
    printf '  %-28s %s FAILED\n' "$unit" "$verb"
  fi
}

start_all() {
  echo "Starting web frontend..."
  systemctl start "$WEB_SERVICE" 2>/dev/null \
    && printf '  %-28s %s\n' "$WEB_SERVICE" "$(systemctl is-active "$WEB_SERVICE" 2>/dev/null)" \
    || echo "  WARN: could not start $WEB_SERVICE"

  echo "Starting core services..."
  for s in "${SERVICES[@]}"; do do_action start "$s"; done

  echo "Starting timers..."
  for t in "${TIMERS[@]}"; do do_action start "$t"; done
}

stop_all() {
  # Stop timers first (esp. the watchdog) so nothing re-launches services.
  echo "Stopping timers..."
  for t in "${TIMERS[@]}"; do do_action stop "$t"; done

  echo "Stopping core services (reverse order)..."
  for (( i=${#SERVICES[@]}-1 ; i>=0 ; i-- )); do do_action stop "${SERVICES[$i]}"; done

  echo "(Leaving $WEB_SERVICE running; run 'systemctl stop $WEB_SERVICE' to take the web server down too.)"
}

status_all() {
  printf '%-28s %-10s %s\n' "UNIT" "ENABLED" "ACTIVE"
  printf '%-28s %-10s %s\n' "----" "-------" "------"
  local en ac
  for u in "$WEB_SERVICE" "${SERVICES[@]}" "${TIMERS[@]}"; do
    if have_unit "$u"; then
      # `systemctl is-enabled/is-active` PRINT the state and still exit non-zero
      # when it isn't enabled/active, so a `|| echo '-'` fires in addition to the
      # real output ("disabled\n-") and wraps the row. Keep stdout, drop the exit
      # status, and only substitute '-' when nothing was printed at all.
      en=$(systemctl is-enabled "$u" 2>/dev/null) || true
      ac=$(systemctl is-active  "$u" 2>/dev/null) || true
      printf '%-28s %-10s %s\n' "$u" "${en:--}" "${ac:--}"
    else
      printf '%-28s %-10s %s\n' "$u" "-" "MISSING"
    fi
  done
}

enable_all() {
  for u in "${SERVICES[@]}" "${TIMERS[@]}"; do do_action enable "$u"; done
  start_all
}

disable_all() {
  stop_all
  for u in "${SERVICES[@]}" "${TIMERS[@]}"; do do_action disable "$u"; done
}

# ---- main ------------------------------------------------------------------

case "${1:-}" in
  on|start)    start_all ;;
  off|stop)    stop_all ;;
  restart)     stop_all; echo; start_all ;;
  status)      status_all ;;
  enable)      enable_all ;;
  disable)     disable_all ;;
  *)
    echo "Usage: $0 {on|off|restart|status|enable|disable}" >&2
    exit 2
    ;;
esac
