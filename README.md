# GOES HRIT Live Web UI

**A production-grade pipeline for ingesting GOES-18/19 HRIT Full Disk imagery and publishing real-time web endpoints with timelapse generation.**

This repository contains everything required to:

- Ingest GOES-18 and GOES-19 HRIT (High Rate Information Transmission)
- Decode ABI imagery via SatDump
- Select only **complete Full Disk frames**
- Publish real-time web endpoints with Server-Sent Events (SSE)
- Generate animated timelapse GIFs on demand
- Serve via nginx with zero-cache guarantees
- Provide an interactive web UI with Live and Timelapse modes

This is not a demo system - it is designed as **infrastructure**.

---

## System Architecture

```
GOES-18/19 HRIT RF
        |
SDR + LNA + Filter + Dish
        |
SatDump HRIT Decoder
        |
Filesystem (timestamped frames)
   /home/pi/sat/GOES-{18,19}/IMAGES/GOES-{18,19}/Full Disk/
        |
update_goes_multi_web.sh (publisher)
        |
/var/www/goes/current/{GOES-18,GOES-19}/
        |
goes_sse_watch.py (SSE server + timelapse API)
        |
nginx (port 8080)
        |
Web UI (Live + Timelapse modes)
```

---

## Features

### Live Mode
- Real-time satellite image display
- Satellite selector (GOES-18 / GOES-19)
- Image/band selector
- Auto-refresh via Server-Sent Events
- No browser caching

### Timelapse Mode
- On-demand animated GIF generation
- Configurable band selection (CH2, CH7, CH8, CH13)
- Configurable time window (3h, 6h, 12h, 24h)
- Configurable frame count (12, 24, 36, 48)
- Metadata display (frame count, generation time)

---

## Disk Layout

### SatDump Output

```
/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk/
    2026-01-25_15-30-21/
        G19_2_20260125T153021Z.png   (CH2 Visible)
        G19_7_20260125T153021Z.png   (CH7 Clean IR)
        G19_8_20260125T153021Z.png   (CH8 Water Vapor)
        G19_13_20260125T153021Z.png  (CH13 Longwave IR)
        product.cbor
```

Each directory = one Full Disk frame timestamp.

### Web Root

```
/var/www/goes/
    index.html
    style.css
    app.js
    meta.json
    meta_GOES-18.json
    meta_GOES-19.json
    current/
        GOES-18/
        GOES-19/
    timelapse/
        GOES-19_B13_6h.gif
        GOES-19_B13_6h.json
```

---

## Channel Mapping

| ABI Band | Wavelength | Description |
|----------|------------|-------------|
| CH2 | 0.64 um | Visible (Red) |
| CH7 | 3.9 um | Shortwave IR / Clean IR |
| CH8 | 6.2 um | Upper-level Water Vapor |
| CH13 | 10.3 um | Longwave IR (Clean Window) |

---

## Components

### Scripts

| File | Purpose |
|------|---------|
| `update_goes_multi_web.sh` | Publishes latest frames for all satellites |
| `goes_sse_watch.py` | SSE server + timelapse API (port 8090) |
| `make_timelapse_gif.sh` | Generates animated GIF timelapses |
| `make_timelapse.sh` | Generates MP4 timelapse videos |
| `cleanup_satdump_old.sh` | Removes old SatDump data |

### systemd Units

| File | Purpose |
|------|---------|
| `update-goes-fd-web.service` | Publisher service |
| `update-goes-fd-web.timer` | Runs publisher every minute |
| `goes-sse.service` | SSE server daemon |
| `satdump-cleanup.service` | Cleanup service |
| `satdump-cleanup.timer` | Cleanup timer |
| `satdump-goes19.service` | SatDump decoder service |

### Web Files

| File | Purpose |
|------|---------|
| `index.html` | Main page structure |
| `style.css` | Dark theme styling |
| `app.js` | Live/Timelapse logic + SSE handling |

### nginx

| File | Purpose |
|------|---------|
| `goes-hrit-live.conf` | Server config (port 8080) |

---

## nginx Endpoints

| Path | Description |
|------|-------------|
| `/` | Web UI |
| `/goes/` | Web UI (alias) |
| `/current/{SAT}/` | Latest images per satellite |
| `/timelapse/` | Generated timelapse GIFs |
| `/events` | SSE stream for live updates |
| `/api/timelapse` | POST endpoint for GIF generation |

All paths work with or without `/goes/` prefix.

---

## Installation

### Prerequisites

- Raspberry Pi (tested on RPi5)
- SatDump configured for GOES HRIT
- SDR hardware + dish pointed at GOES

### Quick Install

1. Clone this repo to the Pi:
```bash
git clone <repo-url> ~/goes-hrit-live-webui
cd ~/goes-hrit-live-webui
```

2. Run the installer (as root):
```bash
sudo bash install/install.sh
```

This installs:
- nginx and ffmpeg packages
- Web UI to `/var/www/goes/`
- Scripts to `/usr/local/bin/`
- systemd units to `/etc/systemd/system/`
- nginx config to `/etc/nginx/sites-available/`

3. Open browser:
```
http://<pi-ip>:8080/
```

### Manual Installation

1. Install packages:
```bash
sudo apt-get install -y nginx python3 ffmpeg
```

2. Create web root:
```bash
sudo mkdir -p /var/www/goes/{current,timelapse}
sudo chown -R www-data:www-data /var/www/goes
```

3. Copy files:
```bash
sudo cp web/* /var/www/goes/
sudo cp scripts/*.sh /usr/local/bin/
sudo cp scripts/*.py /usr/local/bin/
sudo chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py
sudo cp systemd/* /etc/systemd/system/
sudo cp nginx/goes-hrit-live.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/goes-hrit-live /etc/nginx/sites-enabled/
```

4. Enable services:
```bash
sudo systemctl daemon-reload
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now goes-sse.service
sudo systemctl enable --now update-goes-fd-web.timer
```

---

## Configuration

### Satellite Paths

Edit `scripts/update_goes_multi_web.sh` to add/modify satellite paths:

```bash
CANDIDATES=(
  "GOES-18:/home/pi/sat/GOES-18/IMAGES/GOES-18/Full Disk"
  "GOES-19:/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk"
)
```

### Timelapse Paths

Edit `scripts/make_timelapse_gif.sh` to change the source path:

```bash
ROOT="/home/pi/sat/${SAT}/IMAGES/${SAT}/Full Disk"
```

---

## Monitoring

### Service Status
```bash
systemctl status goes-sse.service
systemctl status update-goes-fd-web.timer
```

### Logs
```bash
# Publisher logs
journalctl -u update-goes-fd-web.service -f

# SSE server logs
journalctl -u goes-sse.service -f
```

### Timer Status
```bash
systemctl list-timers update-goes-fd-web.timer
```

### Verify Updates
```bash
cat /var/www/goes/meta.json
watch -n 10 cat /var/www/goes/meta.json
```

---

## Troubleshooting

### Images not updating
1. Check if publisher is running: `systemctl status update-goes-fd-web.timer`
2. Check for images: `ls "/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk/" | tail -5`
3. Check logs: `journalctl -u update-goes-fd-web.service -n 50`

### SSE not connecting
1. Check SSE server: `sudo ss -tlnp | grep 8090`
2. Test endpoint: `curl -N http://localhost:8080/events`
3. Check nginx config: `sudo nginx -t`

### Timelapse generation fails
1. Test manually: `sudo /usr/local/bin/make_timelapse_gif.sh GOES-19 13 6 24`
2. Check ffmpeg: `which ffmpeg`
3. Check permissions: `ls -la /var/www/goes/timelapse/`

---

## Design Principles

### Determinism
Only complete datasets are published. Partial frames are never visible.

### Stability
Stable URLs that never change names - only content.

### Idempotence
Publisher can run repeatedly without corruption.

### Zero Caching
All endpoints return `Cache-Control: no-store` headers.

### Real-time Updates
SSE push notifications eliminate polling overhead.

---

## File Structure

```
goes-hrit-live-webui/
    install/
        install.sh          # Main installer
        uninstall.sh        # Cleanup script
        check.sh            # Verification script
    scripts/
        update_goes_multi_web.sh
        goes_sse_watch.py
        make_timelapse_gif.sh
        make_timelapse.sh
        cleanup_satdump_old.sh
        build_mosaic.py
        install_wizard.sh
        run_satdump_goes19.sh
    systemd/
        goes-sse.service
        update-goes-fd-web.service
        update-goes-fd-web.timer
        satdump-cleanup.service
        satdump-cleanup.timer
        satdump-goes19.service
    nginx/
        goes-hrit-live.conf
    web/
        index.html
        style.css
        app.js
    docs/
        SECURITY.md
    README.md
    LICENSE
```

---

## License

Public repository.
Open architecture.
Free use for research, education, and infrastructure.

---
## AUTHOR
Dr. Robert McGwier, PhD
Bob McGwier, N4HY
Science Bob

---

**GOES HRIT Live Web UI**

Built as infrastructure, not a project.
