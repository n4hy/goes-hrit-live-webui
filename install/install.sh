#!/usr/bin/env bash
set -euo pipefail

echo "[1/7] Packages..."
apt-get update -y
apt-get install -y nginx python3

echo "[2/7] Web root..."
mkdir -p /var/www/goes/current
chown -R www-data:www-data /var/www/goes
chmod -R 755 /var/www/goes

echo "[3/7] Web UI files..."
install -m 0644 web/index.html /var/www/goes/index.html
install -m 0644 web/style.css /var/www/goes/style.css
install -m 0644 web/app.js /var/www/goes/app.js

echo "[4/7] Scripts..."
install -m 0755 scripts/update_goes_multi_web.sh /usr/local/bin/update_goes_multi_web.sh
install -m 0755 scripts/goes_sse_watch.py /usr/local/bin/goes_sse_watch.py
install -m 0755 scripts/build_mosaic.py /usr/local/bin/build_mosaic.py
install -m 0755 scripts/make_timelapse.sh /usr/local/bin/make_timelapse.sh

echo "[5/7] systemd units..."
install -m 0644 systemd/goes-sse.service /etc/systemd/system/goes-sse.service
install -m 0644 systemd/update-goes-fd-web.service /etc/systemd/system/update-goes-fd-web.service
install -m 0644 systemd/update-goes-fd-web.timer /etc/systemd/system/update-goes-fd-web.timer

echo "[6/7] nginx site (port 8080)..."
install -m 0644 nginx/goes-hrit-live.conf /etc/nginx/sites-available/goes-hrit-live
ln -sf /etc/nginx/sites-available/goes-hrit-live /etc/nginx/sites-enabled/goes-hrit-live

echo "[7/7] Enable + start..."
systemctl daemon-reload
nginx -t
systemctl reload nginx
systemctl enable --now goes-sse.service
systemctl enable --now update-goes-fd-web.timer

echo "Done. LAN UI: http://<pi>:8080/"
