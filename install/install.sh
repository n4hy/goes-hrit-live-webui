#!/usr/bin/env bash
set -euo pipefail

# Use SUDO_USER if available, otherwise default to 'pi'
GOES_USER="${GOES_USER:-${SUDO_USER:-pi}}"
echo "Installing for user: ${GOES_USER}"

echo "[1/9] Stopping services..."
systemctl stop goes-sse.service 2>/dev/null || true
systemctl stop update-goes-fd-web.timer 2>/dev/null || true
systemctl stop update-goes-fd-web.service 2>/dev/null || true

echo "[2/9] Packages..."
apt-get update -y
apt-get install -y nginx python3 python3-pil python3-numpy ffmpeg

echo "[3/9] Web root..."
mkdir -p /var/www/goes/current
mkdir -p /var/www/goes/timelapse
mkdir -p /var/www/goes/falsecolor
# Allow both service user and www-data (nginx) to access
chown -R "${GOES_USER}:www-data" /var/www/goes
chmod -R 775 /var/www/goes

echo "[4/9] Web UI files..."
install -m 0644 web/index.html /var/www/goes/index.html
install -m 0644 web/style.css /var/www/goes/style.css
install -m 0644 web/app.js /var/www/goes/app.js

echo "[5/9] Scripts..."
mkdir -p /usr/local/etc
install -m 0755 scripts/run_satdump_goes19.sh /usr/local/bin/run_satdump_goes19.sh
install -m 0644 scripts/hrit_strict.json /usr/local/etc/hrit_strict.json
install -m 0755 scripts/update_goes_multi_web.sh /usr/local/bin/update_goes_multi_web.sh
install -m 0755 scripts/goes_sse_watch.py /usr/local/bin/goes_sse_watch.py
install -m 0755 scripts/build_mosaic.py /usr/local/bin/build_mosaic.py
install -m 0755 scripts/make_timelapse.sh /usr/local/bin/make_timelapse.sh
install -m 0755 scripts/make_timelapse_gif.sh /usr/local/bin/make_timelapse_gif.sh
install -m 0755 scripts/make_false_color.py /usr/local/bin/make_false_color.py
install -m 0755 scripts/list_history.py /usr/local/bin/list_history.py

echo "[6/9] systemd units..."
# Install and patch service files with correct user
for svc in goes-sse.service update-goes-fd-web.service; do
  sed "s/User=pi/User=${GOES_USER}/g; s/Group=pi/Group=${GOES_USER}/g" \
    "systemd/${svc}" > "/etc/systemd/system/${svc}"
  chmod 0644 "/etc/systemd/system/${svc}"
done
install -m 0644 systemd/update-goes-fd-web.timer /etc/systemd/system/update-goes-fd-web.timer

echo "[7/9] nginx site (port 8080)..."
install -m 0644 nginx/goes-hrit-live.conf /etc/nginx/sites-available/goes-hrit-live
ln -sf /etc/nginx/sites-available/goes-hrit-live /etc/nginx/sites-enabled/goes-hrit-live

echo "[8/9] Reload and start services..."
systemctl daemon-reload
nginx -t
systemctl reload nginx
systemctl enable --now goes-sse.service
systemctl enable --now update-goes-fd-web.timer

echo "[9/9] Set permissions..."
chown -R "${GOES_USER}:www-data" /var/www/goes/timelapse
chown -R "${GOES_USER}:www-data" /var/www/goes/falsecolor
chmod -R 775 /var/www/goes/timelapse
chmod -R 775 /var/www/goes/falsecolor

echo ""
echo "Done. Services running:"
systemctl is-active goes-sse.service || true
systemctl is-active update-goes-fd-web.timer || true
echo ""
echo "LAN UI: http://<pi>:8080/"
