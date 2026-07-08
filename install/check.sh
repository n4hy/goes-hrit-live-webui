#!/usr/bin/env bash
set -euo pipefail

fail=0
pass() { echo "PASS: $*"; }
failm() { echo "FAIL: $*"; fail=1; }

nginx -t >/dev/null 2>&1 && pass "nginx config valid" || failm "nginx config invalid"

for svc in satdump-goes19.service goes-scheduler.service goes-sse.service; do
  systemctl is-active --quiet "$svc" && pass "$svc active" || failm "$svc not active"
done
for tmr in update-goes-fd-web.timer cleanup-bad-frames.timer satdump-cleanup.timer \
           check-rtlsdr.timer goes-web-watchdog.timer; do
  systemctl is-active --quiet "$tmr" && pass "$tmr active" || failm "$tmr not active"
done

curl -sS http://localhost:8080/ >/dev/null 2>&1 && pass "UI reachable :8080" || failm "UI not reachable :8080"
curl -sS -m 2 http://localhost:8080/events >/dev/null 2>&1 && pass "events reachable" || failm "events not reachable"
/usr/local/bin/update_goes_multi_web.sh >/dev/null 2>&1 && pass "publisher ran" || failm "publisher failed"

exit "$fail"
