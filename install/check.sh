#!/usr/bin/env bash
set -euo pipefail

fail=0
pass() { echo "PASS: $*"; }
failm() { echo "FAIL: $*"; fail=1; }

nginx -t >/dev/null 2>&1 && pass "nginx config valid" || failm "nginx config invalid"
systemctl is-active --quiet goes-sse.service && pass "goes-sse.service active" || failm "goes-sse.service not active"
systemctl is-active --quiet update-goes-fd-web.timer && pass "update-goes-fd-web.timer active" || failm "timer not active"
curl -sS http://localhost:8080/ >/dev/null 2>&1 && pass "UI reachable :8080" || failm "UI not reachable :8080"
curl -sS -m 2 http://localhost:8080/events >/dev/null 2>&1 && pass "events reachable" || failm "events not reachable"
/usr/local/bin/update_goes_multi_web.sh >/dev/null 2>&1 && pass "publisher ran" || failm "publisher failed"

exit "$fail"
