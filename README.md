# GOES‑19 Full Disk Web Publisher

**A deterministic, self‑healing, production‑grade pipeline for ingesting GOES‑19 HRIT Full Disk imagery and publishing stable, continuously updating web endpoints.**

This repository contains everything required to:

• Ingest GOES‑19 HRIT (High Rate Information Transmission)
• Decode ABI imagery
• Select only **complete Full Disk frames**
• Enforce data‑settling guarantees (no partial files)
• Publish stable web endpoints (`latest_*.png`)
• Serve via nginx
• Auto‑heal via systemd watchdog
• Provide deterministic updates
• Provide a clean web UI

This is not a demo system — it is designed as **infrastructure**.

---

# System Architecture

```
GOES‑19 HRIT RF
        ↓
SDR + LNA + Filter + Dish
        ↓
SatDump HRIT Decoder
        ↓
Filesystem (timestamped frames)
        ↓
update_goes_fd_web.sh (publisher)
        ↓
/var/www/goes
        ↓
nginx
        ↓
Web UI + stable endpoints
```

---

# Core Design Principles

## 1) Determinism
Only complete datasets are published.
Partial frames are never visible.

## 2) Stability
Stable URLs:

```
/latest_false_color.png
/latest_clean_ir.png
/latest_longwave_ir.png
/latest_wv_upper.png
/meta.json
```

These never change names — only content.

## 3) Temporal Safety
Files must be **settled** before publication:

```bash
SETTLE_SECONDS=90
```

This prevents race conditions while SatDump is still writing.

## 4) Idempotence
Publisher can run repeatedly without corruption.

## 5) Self‑Healing
A watchdog monitors freshness and automatically recovers.

---

# Disk Layout

## SatDump Output

```
/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk/
    2026-01-04_19-00-22/
        G19_2_*.png   (CH2 Visible)
        G19_7_*.png   (CH7 Clean IR / Shortwave IR)
        G19_8_*.png   (CH8 Upper Water Vapor)
        G19_13_*.png  (CH13 Longwave IR)
```

Each directory = one Full Disk frame timestamp.

---

## Web Root

```
/var/www/goes/
    index.html
    meta.json
    latest_false_color.png
    latest_clean_ir.png
    latest_longwave_ir.png
    latest_wv_upper.png
    current/
```

---

# Channel Mapping

| ABI Band | Meaning | Web Output |
|------|------|------|
| CH2 | Visible | latest_false_color.png |
| CH7 | Shortwave IR | latest_clean_ir.png |
| CH8 | Upper Water Vapor | latest_wv_upper.png |
| CH13 | Longwave IR | latest_longwave_ir.png |

---

# Publisher Logic

File:  
```
/usr/local/bin/update_goes_fd_web.sh
```

## Selection Algorithm

1. Sort timestamp directories (newest first)
2. For each directory:
   - Must contain CH2, CH7, CH8, CH13
   - Files must be older than `SETTLE_SECONDS`
3. First directory that passes → selected

This guarantees:
• No partial frames
• No torn writes
• No mixed timestamps

---

## Publication Actions

```
/meta.json                 ← timestamp + UTC update time
/latest_false_color.png    ← CH2
/latest_clean_ir.png       ← CH7
/latest_longwave_ir.png    ← CH13
/latest_wv_upper.png       ← CH8
```

Ownership:
```
www-data:www-data
```

---

# meta.json Format

```json
{
  "timestamp_dir": "2026-01-04_19-30-22",
  "updated_utc": "2026-01-04T20:00:42Z"
}
```

This provides:
• determinism
• observability
• automation hooks
• validation

---

# nginx Configuration

## Primary Server

```
listen 8080;
root /var/www/goes;
```

## Alias Compatibility

```
/goes/  → /var/www/goes/
```

This allows both:
```
/meta.json
/goes/meta.json
```

---

# Web UI

Features:

• Stable image endpoints
• No caching
• Auto refresh
• Deterministic refresh
• Labeled channels
• Single‑page interface

Captions:

• CH2 (Visible) — False color proxy
• CH7 — Clean IR (3.9 µm)
• CH13 — Longwave IR (10.3 µm)
• CH8 — Upper‑level water vapor

---

# Timers

## Publisher Timer

```
update-goes-fd-web.timer
```

Runs publisher automatically.

---

## Watchdog Timer

```
goes-web-watchdog.timer
```

Functions:

• Detect stale data
• Verify file ages
• Verify meta freshness
• Restart SatDump if needed
• Re‑publish if needed
• Prevent restart storms
• Enforce cooldowns

---

# Watchdog Behavior Model

```
FRESH → do nothing
STALE → publish
STALE x N → restart SatDump
COOLDOWN → wait
RECOVER → reset counters
```

This is a **finite‑state recovery machine**, not a cron script.

---

# Why This Is Stable

• No filename mutation
• No directory races
• No partial visibility
• No dependency on SatDump timing
• No UI race conditions
• No HTTP caching
• No symbolic links
• No symlink flips
• No file renames

Only atomic copy + overwrite.

---

# Operational Model

**Deterministic until it fails, then adaptive.**

Normal mode:
• Deterministic publish cycle

Failure mode:
• Detection
• Isolation
• Recovery
• Stabilization
• Resume

---

# What This System Is

• Infrastructure
• Data pipeline
• Deterministic publishing system
• Observability platform
• Real‑time geophysical data service

---

# What This System Is Not

• Demo script
• Hobby pipeline
• "best effort" system
• fire‑and‑forget cron job

---

# Future‑Proofing

Designed to support:

• Mesoscale sectors
• Multi‑sat relay
• GOES‑West integration
• Himawari relay
• EMWIN ingestion
• DCS ingestion
• Multi‑product compositing
• AI segmentation
• Temporal differencing
• Change detection
• Motion vectors
• Event detection

---

# Installation Flow (Novice‑Friendly)

1) Install SatDump
2) Configure HRIT for GOES‑19
3) Set output directory:

```
/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk
```

4) Install nginx

5) Deploy repo files:

```
/usr/local/bin/update_goes_fd_web.sh
/etc/systemd/system/update-goes-fd-web.service
/etc/systemd/system/update-goes-fd-web.timer
/etc/systemd/system/goes-web-watchdog.service
/etc/systemd/system/goes-web-watchdog.timer
/var/www/goes/
```

6) Enable timers:

```
systemctl daemon-reload
systemctl enable --now update-goes-fd-web.timer
tystemctl enable --now goes-web-watchdog.timer
```

7) Open browser:

```
http://<host>:8080/
```

---

# Philosophy

This system is built on:

• Deterministic state machines
• Observable invariants
• Controlled mutation
• Stable interfaces
• Fault isolation
• Minimal coupling
• Predictable behavior

This is how infrastructure is built — not scripts.

---

# Status

**Operational**

• Continuous publishing
• Stable endpoints
• Deterministic behavior
• Self‑healing
• Full Disk only
• No partial frames
• Labeled channels
• Production stability

---

# Author’s Note

This system intentionally prioritizes:

• correctness over speed
• determinism over novelty
• stability over features
• invariants over convenience
• architecture over hacks

Because once it’s stable — everything else becomes easy.

---

# License

Public repository.  
Open architecture.  
Free use for research, education, and infrastructure.

---

**GOES‑19 Full Disk Web Publisher**

Built as infrastructure, not a project.

