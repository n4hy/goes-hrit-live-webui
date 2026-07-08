#!/usr/bin/env bash
set -euo pipefail

# Removes the GOES HRIT pipeline units, scripts and nginx site.
# Config files under /etc and data under /var are left in place on purpose.

echo "Disabling services and timers..."
for u in satdump-goes19.service goes-scheduler.service goes-sse.service \
         update-goes-fd-web.timer update-goes-fd-web.service \
         cleanup-bad-frames.timer cleanup-bad-frames.service \
         satdump-cleanup.timer satdump-cleanup.service \
         check-rtlsdr.timer check-rtlsdr.service \
         goes-web-watchdog.timer goes-web-watchdog.service; do
  systemctl disable --now "$u" 2>/dev/null || true
done

echo "Removing unit files..."
for u in satdump-goes19.service goes-scheduler.service goes-sse.service \
         update-goes-fd-web.timer update-goes-fd-web.service \
         cleanup-bad-frames.timer cleanup-bad-frames.service \
         satdump-cleanup.timer satdump-cleanup.service \
         check-rtlsdr.timer check-rtlsdr.service \
         goes-web-watchdog.timer goes-web-watchdog.service; do
  rm -f "/etc/systemd/system/${u}"
done
systemctl daemon-reload

echo "Removing scripts..."
for s in run_satdump_goes19.sh update_goes_multi_web.sh goes_scheduler.py \
         goes_composites.py goes_sse_watch.py validate_hrit_image.py build_mosaic.py \
         make_timelapse.sh make_timelapse_gif.sh make_false_color.py list_history.py \
         validate_frame.py cleanup_bad_frames.sh cleanup_satdump_old.sh check_rtlsdr.sh \
         goes_web_watchdog.sh log_frame_stats.sh show_frame_stats.sh; do
  rm -f "/usr/local/bin/${s}"
done

echo "Removing nginx site..."
rm -f /etc/nginx/sites-enabled/goes-hrit-live
rm -f /etc/nginx/sites-available/goes-hrit-live
nginx -t && systemctl reload nginx || true

echo "Uninstalled. (/etc configs and /var data preserved.)"
