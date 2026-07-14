# GOES HRIT Live Web UI

**A production-grade pipeline for ingesting GOES-18/19 HRIT imagery and publishing real-time web endpoints with full-featured satellite imagery analysis.**

This repository contains everything required to:

- Ingest GOES-18 and GOES-19 HRIT (High Rate Information Transmission)
- Decode ABI imagery via SatDump
- Support **Full Disk, Mesoscale 1, and Mesoscale 2** sectors
- Publish real-time web endpoints with Server-Sent Events (SSE)
- Browse historical imagery with frame-by-frame navigation
- Generate animated timelapse GIFs on demand
- Generate false color composites from multiple bands
- Display EMWIN (Emergency Managers Weather Information Network) text products
- Serve via nginx with zero-cache guarantees

This is not a demo system - it is designed as **infrastructure**.

> ### ⏸️ This deployment is currently OFF
>
> As of **2026-07-14** the pipeline is stopped and **disabled at boot**, on purpose.
> This Pi is also used for CPU kernel benchmarking, and the per-frame
> `make_false_color.py` worker holds a full core — on a 4-core machine that
> silently corrupts any measurement running beside it.
>
> **GOES-19 is not recording while it is off, and missed imagery cannot be
> backfilled.** The web UI under `/var/www/goes` still serves whatever was last
> published, but stops updating.
>
> ```bash
> sudo ./goes_run status    # what is actually running right now
> sudo ./goes_run on        # bring it back for this boot only
> sudo ./goes_run on y      # bring it back permanently (re-enables at boot)
> ```
>
> See [System On/Off Control](#system-onoff-control). Nothing about the install is
> broken — it is switched off, and `goes_run on` is all it takes.

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
   /home/pi/sat/GOES-{18,19}/IMAGES/GOES-{18,19}/{Full Disk,Mesoscale 1,Mesoscale 2}/
        |
goes_scheduler.py (predictive publisher + composites + retention)
        |
/var/www/goes/current/{GOES-18,GOES-19}/
   channel PNGs, composite PNGs (auto-cleaned after retention_days)
        |
goes_sse_watch.py (SSE server + all APIs)
        |
nginx (port 8080)
        |
Web UI (Live + History + Timelapse + False Color + EMWIN modes)
```

---

## Features

### Live Mode
- Real-time satellite image display
- Satellite selector (GOES-18 / GOES-19)
- Sector selector (Full Disk, Mesoscale 1, Mesoscale 2)
- Image/band selector
- Auto-refresh via Server-Sent Events
- 15-minute fallback refresh if SSE updates stop
- No browser caching

### History Mode
- Browse historical imagery frame-by-frame
- Navigation controls (First, Previous, Next, Last)
- Dropdown selector for direct frame access
- Available bands shown per frame
- Sorted by timestamp (newest first)

### Timelapse Mode
- On-demand animated GIF generation
- Configurable band selection (CH2, CH7, CH8, CH13)
- Configurable time window (3h, 6h, 12h, 24h)
- Configurable frame count (12, 24, 36, 48)
- **Reject bad frames** - filters out corrupt frames with missing data (black bands)
- **Save GIF button** - download generated timelapses directly
- Smart gap-filling: when corrupt frames are rejected, adjacent valid frames are used
- Evenly-spaced target timestamps maintain smooth animation
- Metadata display (frame count, generation time)

### False Color Mode
- On-demand false color composite generation
- **Auto-regeneration** on new frame arrival (triggered by SSE watcher)
- **Band quality gating** - rejects bands with data-loss rows (black band corruption)
- **Timestamp matching** - all bands in a composite must share the same observation timestamp
- **Automatic fallback** - skips corrupt/incomplete frames and tries the next-oldest
- Seven preset algorithms:
  - **Day/Night** - Visible by day, IR by night (GeoColor-style) — requires CH2, CH13
  - **Fire/Hot Spot** - CH7 shortwave IR highlights fires and hot spots — requires CH2, CH7, CH13
  - **Vegetation** - Enhanced vegetation visibility — requires CH2, CH7
  - **Sandwich RGB** - Visible + IR blend for cloud texture — requires CH2, CH13
  - **Water Vapor** - CH8 (6.2um) upper-level water vapor visualization — requires CH8, CH13
  - **GeoEarthDay** - True color composite using Bah et al. green synthesis — requires CH1, CH2, CH3
  - **Custom RGB** - User-selectable R/G/B band assignments
- Custom mode allows any combination of available bands (CH2, CH7, CH8, CH13, CH14)

### EMWIN Mode
- Emergency Managers Weather Information Network products
- Text products (forecasts, warnings, bulletins)
- Graphics products (radar images, satellite composites)
- Auto-discovery of EMWIN product directories
- Recent products list with refresh
- Full-text product display with monospace formatting
- Sorted by modification time (newest first)
- Automatic cleanup of products older than 7 days

### Signal Quality Overlay
- **Today total images** and **Broken percentage** displayed in the upper-right corner of the image viewer
- Visible in all modes except Timelapse (where GIF playback takes priority)
- Gives users an at-a-glance view of signal collection degradation — a rising broken percentage indicates antenna, LNA, feedline, or RF interference issues before they become critical
- Stats computed in the background on each new frame arrival; cached per-image to avoid redundant validation
- Color-coded: green when broken rate is under 10%, red when above

### RTL-SDR Disconnect Alarm
- Detects when the RTL-SDR USB dongle is unplugged or unresponsive
- **Web UI banner** - red "RTL-SDR DISCONNECTED" banner appears across the top of the page
- **Desktop popup** - large red `yad` dialog on the Pi desktop (auto-dismissed when dongle returns)
- Web UI polls `/api/rtlsdr` every 60 seconds; systemd timer checks USB every 5 minutes
- Vendor/product ID `0bda:2838` checked via `lsusb`

### Bad Frame Protection
- Automatic detection of frames with black bar corruption
- Corrupt frames rejected before publishing (never displayed in live view)
- Background cleanup deletes bad frames from source directories
- Statistics tracking for RF health monitoring
- Protects all display modes: live, history, timelapse, false color

---

## Disk Layout

### SatDump Output

```
/home/pi/sat/GOES-19/IMAGES/GOES-19/
    Full Disk/
        2026-01-25_15-30-21/
            G19_1_20260125T153021Z.png   (CH1 Blue Visible)
            G19_2_20260125T153021Z.png   (CH2 Red Visible)
            G19_3_20260125T153021Z.png   (CH3 Near-IR Veggie)
            G19_7_20260125T153021Z.png   (CH7 Clean IR)
            G19_8_20260125T153021Z.png   (CH8 Water Vapor)
            G19_13_20260125T153021Z.png  (CH13 Longwave IR)
            product.cbor
    Mesoscale 1/
        2026-01-25_15-30-21/
            ...
    Mesoscale 2/
        2026-01-25_15-30-21/
            ...
/home/pi/sat/GOES-19/EMWIN/
    *.txt, *.TXT (weather text products)
    *.GIF, *.JPG, *.PNG (weather graphics)
```

Each directory = one frame timestamp.

### Web Root

```
/var/www/goes/
    index.html
    style.css
    app.js
    meta.json
    meta_GOES-18_Full_Disk.json
    meta_GOES-19_Full_Disk.json
    meta_GOES-19_Mesoscale_1.json
    ...
    current/
        GOES-18/
            Full_Disk/
            Mesoscale_1/
            Mesoscale_2/
        GOES-19/
            G19_2_20260125T153021Z.png   (published channels)
            G19_7_20260125T153021Z.png
            G19_13_20260125T153021Z.png
            composite_nighttime_microphysics_20260125T153021Z.png
            composite_split_window_20260125T153021Z.png
            Full_Disk/
            Mesoscale_1/
            Mesoscale_2/
    timelapse/
        GOES-19_B13_6h.gif
        GOES-19_B13_6h.json
    falsecolor/
        GOES-19_daynight.png
        GOES-19_fire.png
        GOES-19_geoearthday.png
        GOES-19_custom_R2_G7_B13.png
```

---

## Channel Mapping

| ABI Band | Wavelength | Description |
|----------|------------|-------------|
| CH1 | 0.47 um | Visible (Blue) |
| CH2 | 0.64 um | Visible (Red) |
| CH3 | 0.86 um | Near-IR (Veggie) |
| CH7 | 3.9 um | Shortwave IR / Clean IR |
| CH8 | 6.2 um | Upper-level Water Vapor |
| CH13 | 10.3 um | Longwave IR (Clean Window) |

---

## Components

### Scripts

| File | Purpose |
|------|---------|
| `goes_scheduler.py` | Predictive publisher + composites + image retention cleanup |
| `goes_composites.py` | Generates composite images (nighttime microphysics, split window, day convection) |
| `update_goes_multi_web.sh` | Legacy publisher for all satellites/sectors (replaced by scheduler) |
| `goes_sse_watch.py` | SSE server + all APIs (port 8090) |
| `list_history.py` | Lists historical frames for history browser |
| `make_timelapse_gif.sh` | Generates animated GIF timelapses |
| `make_timelapse.sh` | Generates MP4 timelapse videos |
| `make_false_color.py` | Generates false color composite images |
| `cleanup_satdump_old.sh` | Removes old SatDump data and EMWIN products |
| `validate_frame.py` | Detects black bar corruption in frames |
| `cleanup_bad_frames.sh` | Scans and deletes corrupt frames |
| `log_frame_stats.sh` | Logs frame validation statistics |
| `show_frame_stats.sh` | Displays RF health statistics |
| `check_rtlsdr.sh` | RTL-SDR disconnect alarm (desktop popup) |
| `goes_web_watchdog.sh` | Self-healing watchdog: reruns publisher / restarts SatDump if web output goes stale |
| `goes_run` | On/off front door: `goes_run on\|off [y\|n]`, where `y` makes it permanent across reboots (repo root) |
| `OnOff.sh` | Implementation behind `goes_run` — unit ordering and start/stop/enable/disable (repo root, not installed to `/usr/local/bin`) |

### systemd Units

| File | Purpose |
|------|---------|
| `goes-scheduler.service` | Predictive scheduler: publishes, generates composites, cleans old images |
| `update-goes-fd-web.service` | Legacy publisher service |
| `update-goes-fd-web.timer` | Runs legacy publisher every minute |
| `goes-sse.service` | SSE server daemon |
| `satdump-cleanup.service` | Data cleanup service (SatDump + EMWIN) |
| `satdump-cleanup.timer` | Runs cleanup daily at midnight |
| `satdump-goes19.service` | SatDump decoder service |
| `cleanup-bad-frames.service` | Bad frame cleanup service |
| `cleanup-bad-frames.timer` | Runs cleanup every 15 minutes |
| `check-rtlsdr.service` | RTL-SDR disconnect checker |
| `check-rtlsdr.timer` | Runs RTL-SDR check every 5 minutes |
| `goes-web-watchdog.service` | Self-healing watchdog run |
| `goes-web-watchdog.timer` | Runs the watchdog every 2 minutes |

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
| `/current/{SAT}/{SECTOR}/` | Latest images per satellite/sector |
| `/timelapse/` | Generated timelapse GIFs |
| `/falsecolor/` | Generated false color composites |
| `/events` | SSE stream for live updates |
| `/api/timelapse` | POST - Generate timelapse GIF |
| `/api/falsecolor` | POST - Generate false color composite |
| `/api/history` | GET - List historical frames |
| `/api/emwin` | GET - List EMWIN products |
| `/api/emwin/read` | GET - Read EMWIN product content |
| `/api/sectors` | GET - List available satellites/sectors |
| `/api/stats` | GET - Today's image count and broken percentage |
| `/api/validation` | GET/POST - Get or set image validation enabled/disabled |
| `/api/rtlsdr` | GET - RTL-SDR USB dongle connection status |

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
- nginx, ffmpeg, python3-pil, python3-numpy, jq packages
- Web UI to `/var/www/goes/`
- Scripts to `/usr/local/bin/`
- systemd units to `/etc/systemd/system/`
- Config templates to `/etc/` (`goes-scheduler.json`, `goes_watchdog.conf`, `satdump_cleanup.conf`) — only if not already present, so local edits are preserved
- nginx config to `/etc/nginx/sites-available/`

It then enables and starts the full pipeline: `satdump-goes19`, `goes-sse`,
`goes-scheduler`, and the publisher/cleanup/RTL-SDR/watchdog timers.

3. Open browser:
```
http://<pi-ip>:8080/
```

### System On/Off Control

`goes_run` (repo root) is the front door. It starts or stops the entire real-time
system as a unit — RF ingest, SSE/API, scheduler, and all maintenance timers — in
the correct dependency order. The second argument says whether the change is
**permanent** (survives a reboot):

```bash
sudo ./goes_run on        # start now; still off after a reboot   (n is the default)
sudo ./goes_run on  n     # same as above, explicit
sudo ./goes_run on  y     # start now AND come back on every boot
sudo ./goes_run off       # stop now; boot setting unchanged
sudo ./goes_run off y     # stop now AND stay off across reboots
sudo ./goes_run restart   # stop then start
sudo ./goes_run status    # show enabled/active state of every unit
```

> **The stack is currently disabled at boot (since 2026-07-14), deliberately.**
> The per-frame `make_false_color.py` worker holds a full core, and on a 4-core Pi
> that wrecks any benchmark running beside it. `n` is the default precisely so a
> quick `goes_run on` cannot silently undo that — changing the boot behaviour
> takes an explicit `y`.
>
> While the stack is off, **GOES-19 is not recording** — missed imagery cannot be
> backfilled — and `/var/www/goes` stops updating. `goes_run on` resumes both.

`goes_run` delegates to **`OnOff.sh`**, which holds the actual unit logic and can
still be called directly (`on|off|restart|status|enable|disable`, where
`enable`/`disable` are the permanent forms).

Notes:
- The watchdog timer is stopped **first** on shutdown so it cannot restart
  SatDump mid-teardown, and services start in order (ingest → SSE → scheduler → timers).
- `off` leaves **nginx** running so the web server (and your SSH-independent
  access to it) stays up; run `sudo systemctl stop nginx` to take it down too.
- Both scripts self-elevate with `sudo` if not run as root.
- `check-rtlsdr.timer` is listed in the stack but is intentionally left **enabled**
  while the rest is off: it only runs `lsusb` to raise the dongle-unplugged alarm,
  costs nothing, and serves the RTL-SDR generally (not just GOES).

### Manual Installation

1. Install packages:
```bash
sudo apt-get install -y nginx python3 python3-pip ffmpeg
pip3 install pillow numpy
```

2. Create web root:
```bash
sudo mkdir -p /var/www/goes/{current,timelapse,falsecolor}
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

### Satellite/Sector Paths

Edit `scripts/update_goes_multi_web.sh` to add/modify satellite and sector paths:

```bash
CANDIDATES=(
  "GOES-18:Full Disk:/home/pi/sat/GOES-18/IMAGES/GOES-18/Full Disk"
  "GOES-19:Full Disk:/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk"
  "GOES-18:Mesoscale 1:/home/pi/sat/GOES-18/IMAGES/GOES-18/Mesoscale 1"
  "GOES-19:Mesoscale 1:/home/pi/sat/GOES-19/IMAGES/GOES-19/Mesoscale 1"
  "GOES-18:Mesoscale 2:/home/pi/sat/GOES-18/IMAGES/GOES-18/Mesoscale 2"
  "GOES-19:Mesoscale 2:/home/pi/sat/GOES-19/IMAGES/GOES-19/Mesoscale 2"
)
```

### EMWIN Paths

The system auto-discovers EMWIN directories. Edit `scripts/goes_sse_watch.py` to add search paths:

```python
EMWIN_PATHS = [
    "/home/pi/sat/GOES-19/EMWIN",
    "/home/pi/sat/GOES-19/PRODUCTS/EMWIN",
    "/home/pi/sat/goes19/EMWIN",
]
```

### EMWIN Cleanup

EMWIN products (txt, gif, jpg, png) older than 7 days are automatically deleted by the daily cleanup at midnight. Configure retention in `/etc/satdump_cleanup.conf`:

```bash
EMWIN_MAX_DAYS=7   # Days to retain EMWIN products (default: 7)
```

### Timelapse Paths

Edit `scripts/make_timelapse_gif.sh` to change the source path:

```bash
ROOT="/home/pi/sat/${SAT}/IMAGES/${SAT}/Full Disk"
```

### Timelapse Gap-Filling Algorithm

When generating timelapses with `--reject-bad`, corrupt frames are excluded. To maintain smooth animation:

1. **Target timestamps** are calculated evenly across the time window
2. For each target, the **nearest valid frame** is selected
3. If a frame is already used or corrupt, **adjacent valid frames** are randomly chosen
4. This minimizes visual jumps from missing frames

Example: 24h timelapse with 48 frames = target every 30 minutes. If the 12:00 frame is corrupt, the 11:30 or 12:30 frame is used instead.

---

## GOES Scheduler

The `goes_scheduler.py` service replaces blind polling with predictive scheduling. It observes frame arrival times, learns the publication interval, and sleeps until the next expected frame instead of constantly polling.

### Features

- **Schedule Learning** - Observes frame arrivals and calculates mean interval + stddev
- **Predictive Polling** - Sleeps until expected arrival time with tolerance window
- **Automatic Relearning** - After 3 consecutive missed frames, re-enters learning mode
- **Channel Publishing** - Copies channel PNGs (CH2, CH7, CH8, CH13) to the web directory
- **Composite Generation** - Generates Nighttime Microphysics, Split Window, and Day Convection composites via `goes_composites.py`
- **Image Retention** - Automatically deletes published images older than `retention_days` (default: 2 days)

### Configuration

Configuration file: `/etc/goes-scheduler.json`

Key settings (all have defaults in `goes_scheduler.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `retention_days` | `2` | Days to keep published channel/composite images |
| `satellites` | GOES-19 | Satellite roots and channel glob patterns |
| `composites` | all enabled | Which composites to generate |
| `schedule.learning_observations` | `6` | Observations before transitioning to learned mode |
| `schedule.relearn_threshold` | `3` | Consecutive failures before relearning |
| `schedule.default_interval_seconds` | `600` | Default polling interval (10 min) |
| `schedule.fallback_poll_seconds` | `60` | Polling interval during learning mode |

The config uses deep merging - you can override individual keys without losing unspecified defaults.

### State

State file: `/var/lib/goes-publisher/schedule_state.json`

Persists learned schedule, observations, and failure counts across restarts.

### Image Retention

Published channel and composite images accumulate in `/var/www/goes/current/{SAT}/`. The scheduler automatically cleans images older than `retention_days`:

- **On publish** - cleanup runs after each new frame is published
- **Hourly** - cleanup runs independently every hour, even if no new data arrives (prevents disk exhaustion during satellite outages)

Timestamps are extracted from filenames (e.g., `G19_13_20260125T153021Z.png`) and compared against the cutoff.

### Monitoring

```bash
# Service status
systemctl status goes-scheduler.service

# Live logs
journalctl -u goes-scheduler -f

# Check learned state
cat /var/lib/goes-publisher/schedule_state.json | python3 -m json.tool
```

---

## Bad Frame Protection

GOES HRIT reception can produce frames with horizontal black bands due to:
- Incomplete data reception
- RF interference
- Signal degradation (rain fade, antenna issues)
- Demodulation errors

The system automatically detects and removes these corrupt frames.

### How It Works

1. **Publisher Validation** (`update_goes_multi_web.sh`)
   - Validates each Full Disk frame before publishing
   - Corrupt frames are rejected and never displayed in live view
   - Falls back to older directories if newest has all-bad frames
   - Logs rejections to `/var/log/goes/rejected_frames.log`

2. **Background Cleanup** (`cleanup_bad_frames.sh`)
   - Runs every 15 minutes via systemd timer
   - Scans last 6 hours of Full Disk frames
   - Deletes corrupt frames from source directories
   - Removes bad frames from history mode
   - Logs deletions to `/var/log/goes/deleted_frames.log`

3. **Detection Algorithm** (`validate_frame.py`)
   - Zero-tolerance: ANY row with all identical pixels = corrupt
   - Real satellite data always has pixel variation
   - Analyzes center disk region (avoids image border artifacts)
   - Simple and reliable - no false negatives

### RF Health Statistics

Corruption rate tracks RF system health over time. Statistics are logged to CSV:

```
/var/log/goes/frame_stats.csv
```

**View statistics:**
```bash
show_frame_stats.sh           # Formatted table with summary
show_frame_stats.sh --csv     # Raw CSV for analysis
show_frame_stats.sh --hours 6 # Filter to last 6 hours
```

**Example output:**
```
=== GOES Frame Validation Statistics ===

Timestamp            Source           Scanned Rejected     Rate  Note
-------------------- --------------- -------- -------- --------  ----
2026-02-02T18:14:45Z cleanup-6h           93       26    28.0%  errors=0
2026-02-02T19:00:00Z publish-hourly       42        3     7.1%  hour=18

--- Summary (last 24 hours) ---
Total scanned: 135
Total rejected: 29
Overall corruption rate: 21.5%
```

**Interpreting corruption rate:**
| Rate | Interpretation |
|------|----------------|
| < 5% | Excellent - optimal RF conditions |
| 5-15% | Normal - typical reception |
| 15-30% | Degraded - check system |
| > 30% | Poor - investigate immediately |

**Common causes of high corruption:**
- Antenna misalignment
- LNA degradation or failure
- Feedline damage or water ingress
- Local RF interference
- Weather (rain fade)
- SDR overheating

### Manual Cleanup

Run cleanup manually to purge bad frames:

```bash
# Dry run - show what would be deleted
cleanup_bad_frames.sh --dry-run --hours 24

# Delete bad frames from last 24 hours
cleanup_bad_frames.sh --hours 24

# Full cleanup (all frames, may take several minutes)
cleanup_bad_frames.sh --verbose
```

### Validate a Single Frame

```bash
validate_frame.py /path/to/frame.png
# Exit code: 0 = valid, 1 = corrupt, 2 = error
```

---

## Monitoring

### Service Status
```bash
systemctl status goes-scheduler.service
systemctl status goes-sse.service
systemctl status cleanup-bad-frames.timer
```

### Logs
```bash
# Scheduler logs (publisher + composites + retention cleanup)
journalctl -u goes-scheduler.service -f

# SSE server logs
journalctl -u goes-sse.service -f

# Bad frame cleanup logs
journalctl -u cleanup-bad-frames.service -f
```

### Timer Status
```bash
systemctl list-timers cleanup-bad-frames.timer satdump-cleanup.timer check-rtlsdr.timer
```

### Verify Updates
```bash
cat /var/www/goes/meta.json
watch -n 10 cat /var/www/goes/meta.json
```

### RF Health Statistics
```bash
# View frame validation statistics
show_frame_stats.sh

# View rejection/deletion logs
tail -f /var/log/goes/rejected_frames.log
tail -f /var/log/goes/deleted_frames.log

# Raw stats CSV
cat /var/log/goes/frame_stats.csv
```

### Data Cleanup
```bash
# View cleanup log (SatDump directories + EMWIN products)
tail -f /var/log/satdump_cleanup.log

# Manual cleanup run
sudo /usr/local/bin/cleanup_satdump_old.sh
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

### False color generation fails
1. Test manually: `python3 /usr/local/bin/make_false_color.py GOES-19 daynight`
2. Check PIL/numpy: `python3 -c "from PIL import Image; import numpy"`
3. Check permissions: `ls -la /var/www/goes/falsecolor/`

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
        goes_scheduler.py         # Predictive publisher + composites + retention
        goes_composites.py        # Composite image generation
        update_goes_multi_web.sh  # Legacy publisher for all satellites/sectors
        goes_sse_watch.py         # SSE server + all APIs
        list_history.py           # History frame listing
        make_timelapse_gif.sh     # GIF timelapse generator
        make_timelapse.sh         # MP4 timelapse generator
        make_false_color.py       # False color compositor
        cleanup_satdump_old.sh    # Old data cleanup
        build_mosaic.py           # Image mosaic builder
        install_wizard.sh         # Interactive installer
        run_satdump_goes19.sh     # SatDump runner
        validate_frame.py         # Bad frame detector
        cleanup_bad_frames.sh     # Bad frame cleanup
        log_frame_stats.sh        # Statistics logger
        show_frame_stats.sh       # Statistics viewer
        check_rtlsdr.sh           # RTL-SDR disconnect alarm
    systemd/
        goes-scheduler.service
        goes-sse.service
        update-goes-fd-web.service
        update-goes-fd-web.timer
        satdump-cleanup.service
        satdump-cleanup.timer
        satdump-goes19.service
        cleanup-bad-frames.service
        cleanup-bad-frames.timer
        check-rtlsdr.service
        check-rtlsdr.timer
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

### Log Files

```
/var/log/goes/
    rejected_frames.log   # Frames rejected by publisher
    deleted_frames.log    # Frames deleted by cleanup
    frame_stats.csv       # RF health statistics
    publish_stats.tmp     # Hourly accumulator (internal)

/var/log/satdump_cleanup.log  # SatDump + EMWIN cleanup log

/var/lib/goes-publisher/
    schedule_state.json          # Scheduler learned state

/etc/goes-scheduler.json         # Scheduler configuration
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
