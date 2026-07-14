#!/usr/bin/env bash
set -euo pipefail

# Installs the full GOES HRIT real-time pipeline:
#   ingest (satdump-goes19) -> publisher (goes-scheduler + update-goes-fd-web)
#   -> SSE/API (goes-sse) -> nginx, plus maintenance timers and the self-healing
#   watchdog. Config templates under install/ are copied to /etc only if absent,
#   so local edits are never clobbered.
#
# Run from the repo root:  sudo ./install/install.sh

# Use SUDO_USER if available, otherwise default to 'pi'
GOES_USER="${GOES_USER:-${SUDO_USER:-pi}}"
echo "Installing for user: ${GOES_USER}"

echo "[1/11] Stopping services..."
for u in goes-sse.service goes-scheduler.service \
         update-goes-fd-web.timer update-goes-fd-web.service \
         cleanup-bad-frames.timer cleanup-bad-frames.service \
         satdump-cleanup.timer satdump-cleanup.service \
         check-rtlsdr.timer check-rtlsdr.service \
         goes-web-watchdog.timer goes-web-watchdog.service; do
  systemctl stop "$u" 2>/dev/null || true
done

echo "[2/11] Packages..."
apt-get update -y
apt-get install -y nginx python3 python3-pil python3-numpy ffmpeg jq

echo "[3/11] Web root, state and log directories..."
mkdir -p /var/www/goes/current
mkdir -p /var/www/goes/timelapse
mkdir -p /var/www/goes/falsecolor
mkdir -p /var/log/goes
mkdir -p /var/lib/goes-publisher
# Allow both service user and www-data (nginx) to access
chown -R "${GOES_USER}:www-data" /var/www/goes
chmod -R 775 /var/www/goes

echo "[4/11] Web UI files..."
install -m 0644 web/index.html /var/www/goes/index.html
install -m 0644 web/style.css /var/www/goes/style.css
install -m 0644 web/app.js /var/www/goes/app.js

echo "[5/11] Scripts..."
mkdir -p /usr/local/etc
install -m 0644 scripts/hrit_strict.json /usr/local/etc/hrit_strict.json
install -m 0755 scripts/run_satdump_goes19.sh /usr/local/bin/run_satdump_goes19.sh
install -m 0755 scripts/update_goes_multi_web.sh /usr/local/bin/update_goes_multi_web.sh
install -m 0755 scripts/goes_scheduler.py /usr/local/bin/goes_scheduler.py
install -m 0755 scripts/goes_composites.py /usr/local/bin/goes_composites.py
install -m 0755 scripts/goes_sse_watch.py /usr/local/bin/goes_sse_watch.py
install -m 0755 scripts/validate_hrit_image.py /usr/local/bin/validate_hrit_image.py
install -m 0755 scripts/build_mosaic.py /usr/local/bin/build_mosaic.py
install -m 0755 scripts/make_timelapse.sh /usr/local/bin/make_timelapse.sh
install -m 0755 scripts/make_timelapse_gif.sh /usr/local/bin/make_timelapse_gif.sh
install -m 0755 scripts/make_false_color.py /usr/local/bin/make_false_color.py
install -m 0755 scripts/list_history.py /usr/local/bin/list_history.py
install -m 0755 scripts/validate_frame.py /usr/local/bin/validate_frame.py
install -m 0755 scripts/cleanup_bad_frames.sh /usr/local/bin/cleanup_bad_frames.sh
install -m 0755 scripts/cleanup_satdump_old.sh /usr/local/bin/cleanup_satdump_old.sh
install -m 0755 scripts/check_rtlsdr.sh /usr/local/bin/check_rtlsdr.sh
install -m 0755 scripts/goes_web_watchdog.sh /usr/local/bin/goes_web_watchdog.sh
install -m 0755 scripts/log_frame_stats.sh /usr/local/bin/log_frame_stats.sh
install -m 0755 scripts/show_frame_stats.sh /usr/local/bin/show_frame_stats.sh

echo "[6/11] Config files (only if not already present)..."
[ -f /etc/goes-scheduler.json ] || install -m 0644 install/goes-scheduler.json /etc/goes-scheduler.json
[ -f /etc/goes_watchdog.conf ]   || install -m 0644 install/goes_watchdog.conf   /etc/goes_watchdog.conf
[ -f /etc/satdump_cleanup.conf ] || install -m 0644 install/satdump_cleanup.conf /etc/satdump_cleanup.conf

echo "[7/11] systemd units..."
# User-scoped units: patch the service user; other units copy verbatim.
for svc in goes-sse.service update-goes-fd-web.service satdump-goes19.service \
           cleanup-bad-frames.service check-rtlsdr.service; do
  sed "s/User=pi/User=${GOES_USER}/g; s/Group=pi/Group=${GOES_USER}/g" \
    "systemd/${svc}" > "/etc/systemd/system/${svc}"
  chmod 0644 "/etc/systemd/system/${svc}"
done
# Units that run as-is (root / no user substitution)
for unit in goes-scheduler.service goes-web-watchdog.service satdump-cleanup.service \
            update-goes-fd-web.timer cleanup-bad-frames.timer satdump-cleanup.timer \
            check-rtlsdr.timer goes-web-watchdog.timer; do
  install -m 0644 "systemd/${unit}" "/etc/systemd/system/${unit}"
done

echo "[8/11] nginx site (port 8080)..."
install -m 0644 nginx/goes-hrit-live.conf /etc/nginx/sites-available/goes-hrit-live
ln -sf /etc/nginx/sites-available/goes-hrit-live /etc/nginx/sites-enabled/goes-hrit-live

echo "[9/11] Reload and enable services..."
systemctl daemon-reload
nginx -t
systemctl reload nginx
# Core pipeline
systemctl enable --now satdump-goes19.service
systemctl enable --now goes-sse.service
systemctl enable --now goes-scheduler.service
# Publisher + maintenance timers
systemctl enable --now update-goes-fd-web.timer
systemctl enable --now cleanup-bad-frames.timer
systemctl enable --now satdump-cleanup.timer
systemctl enable --now check-rtlsdr.timer
systemctl enable --now goes-web-watchdog.timer

echo "[10/11] Permissions..."
chown -R "${GOES_USER}:www-data" /var/www/goes/timelapse /var/www/goes/falsecolor /var/log/goes
chmod -R 775 /var/www/goes/timelapse /var/www/goes/falsecolor /var/log/goes

echo "[11/11] Initial cleanup of bad frames..."
/usr/local/bin/cleanup_bad_frames.sh --hours 24 || true

echo ""
echo "Done. Real-time system status:"
for u in satdump-goes19.service goes-scheduler.service goes-sse.service \
         update-goes-fd-web.timer cleanup-bad-frames.timer satdump-cleanup.timer \
         check-rtlsdr.timer goes-web-watchdog.timer; do
  printf '  %-28s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null)"
done
echo ""
echo "Control the whole pipeline with:  sudo ./goes_run {on|off} [y|n]"
echo "  y = permanent (also enables/disables at boot); n = this boot only (default)"
echo "  also:  sudo ./goes_run {restart|status}"
echo "LAN UI: http://<pi>:8080/"
