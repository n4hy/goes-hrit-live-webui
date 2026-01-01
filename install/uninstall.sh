#!/usr/bin/env bash
set -euo pipefail

systemctl disable --now update-goes-fd-web.timer 2>/dev/null || true
systemctl disable --now goes-sse.service 2>/dev/null || true

rm -f /etc/systemd/system/update-goes-fd-web.timer
rm -f /etc/systemd/system/update-goes-fd-web.service
rm -f /etc/systemd/system/goes-sse.service
systemctl daemon-reload

rm -f /usr/local/bin/update_goes_multi_web.sh
rm -f /usr/local/bin/goes_sse_watch.py
rm -f /usr/local/bin/build_mosaic.py
rm -f /usr/local/bin/make_timelapse.sh

rm -f /etc/nginx/sites-enabled/goes-hrit-live
rm -f /etc/nginx/sites-available/goes-hrit-live
nginx -t && systemctl reload nginx || true

echo "Uninstalled."
