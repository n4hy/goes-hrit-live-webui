# SatDump GOES-19 HRIT (RTL-SDR) – Live Decoder + Full Disk Web Publisher + Auto-Cleanup

This release captures a working, *operational* Raspberry Pi workflow for:
1) running SatDump `live goes_hrit` from an RTL-SDR to decode GOES-19 HRIT/LRIT products,
2) publishing the **latest Full Disk** images to a simple web directory (`/var/www/goes`) with `meta.json`,
3) automatically deleting SatDump output older than a configurable retention window (`TOOOLD_DAYS`) stored in `/etc/satdump_cleanup.conf`.

It is designed for “drop in and run” on a Pi, with **systemd services + timers**, and an interactive installer that prompts for each step.

---

## What you get

### Services / timers
- `satdump-goes19.service`  
  Runs SatDump continuously:
  ```
  satdump live goes_hrit GOES-19 --source rtlsdr --frequency ... --samplerate ... --gain ... --fill_missing --output-directory ...
  ```

- `update-goes-fd-web.service` + `update-goes-fd-web.timer`  
  Periodically finds the newest Full Disk directory that contains an **anchor file** (default: `product.cbor`) and copies a small set of “latest_*.png” images into `/var/www/goes/`, plus writes `/var/www/goes/meta.json`.

- `satdump-cleanup.service` + `satdump-cleanup.timer`  
  Daily cleanup of SatDump output older than `TOOOLD_DAYS` (default: 7) under the data root (default: `/home/pi/sat`), logging to `/var/log/satdump_cleanup.log`.

### Scripts
Drop these into the repository `scripts/` directory (exact content included in this release):
- `install_wizard.sh` – interactive setup script (recommended)
- `run_satdump_goes19.sh` – wrapper for the SatDump `live goes_hrit` command
- `update_goes_fd_web.sh` – publish latest Full Disk images for web UI
- `cleanup_satdump_old.sh` – delete output older than `TOOOLD_DAYS`, with logging

### Configuration
- `/etc/satdump_cleanup.conf`  
  Example:
  ```
  TOOOLD_DAYS=7
  ROOT=/home/pi/sat
  ```
- `/etc/goes_fd_views.conf`  
  Maps “latest_*” names to filenames to copy from the newest Full Disk directory. Example:
  ```
  latest_false_color.png=abi_rgb_GEO_False_Color.png
  latest_clean_ir.png=abi_rgb_Clean_Longwave_IR_Window_Band.png
  latest_longwave_ir.png=abi_rgb_Infrared_Longwave_Window_Band.png
  latest_wv_upper.png=abi_rgb_Upper-Level_Tropospheric_Water_Vapor.png
  ```

---

## Web address for the images

This setup assumes a web server is already serving `/var/www/goes` on port **8080** (as you were using `curl http://localhost:8080/meta.json`).

Once the publisher runs at least once, you should be able to fetch:

- `http://<PI_HOST>:8080/meta.json`
- `http://<PI_HOST>:8080/latest_false_color.png`
- `http://<PI_HOST>:8080/latest_clean_ir.png`
- `http://<PI_HOST>:8080/latest_longwave_ir.png`
- `http://<PI_HOST>:8080/latest_wv_upper.png`

If you have a different web server/port, adjust the server config—not these scripts. The publisher always writes into `/var/www/goes`.

---

## Installation (recommended: interactive wizard)

### 0) Put the scripts in place
From the repository root:
```bash
sudo install -d -m 0755 /usr/local/bin
sudo install -m 0755 scripts/*.sh /usr/local/bin/
```

### 1) Run the wizard
```bash
sudo /usr/local/bin/install_wizard.sh
```

The wizard will:
- confirm SatDump binary path,
- confirm output root directory,
- create `/etc/satdump_cleanup.conf`,
- create `/etc/goes_fd_views.conf` (if missing),
- install systemd unit files,
- enable and start services/timers.

---

## Manual installation (if you prefer)

### 1) Install scripts
```bash
sudo install -d -m 0755 /usr/local/bin
sudo install -m 0755 scripts/run_satdump_goes19.sh /usr/local/bin/
sudo install -m 0755 scripts/update_goes_fd_web.sh    /usr/local/bin/
sudo install -m 0755 scripts/cleanup_satdump_old.sh   /usr/local/bin/
```

### 2) Create cleanup retention config
```bash
sudo tee /etc/satdump_cleanup.conf >/dev/null <<'EOF'
# Days to retain SatDump data
TOOOLD_DAYS=7
# Root of SatDump output (directory that contains goes19/, etc.)
ROOT=/home/pi/sat
EOF
sudo chmod 0644 /etc/satdump_cleanup.conf
```

### 3) Create Full Disk view map (what to publish as latest_*.png)
```bash
sudo tee /etc/goes_fd_views.conf >/dev/null <<'EOF'
latest_false_color.png=abi_rgb_GEO_False_Color.png
latest_clean_ir.png=abi_rgb_Clean_Longwave_IR_Window_Band.png
latest_longwave_ir.png=abi_rgb_Infrared_Longwave_Window_Band.png
latest_wv_upper.png=abi_rgb_Upper-Level_Tropospheric_Water_Vapor.png
EOF
sudo chmod 0644 /etc/goes_fd_views.conf
```

### 4) Install systemd unit files
Copy the unit files from `systemd/` in this release:
```bash
sudo install -d -m 0755 /etc/systemd/system
sudo install -m 0644 systemd/satdump-goes19.service        /etc/systemd/system/
sudo install -m 0644 systemd/update-goes-fd-web.service    /etc/systemd/system/
sudo install -m 0644 systemd/update-goes-fd-web.timer      /etc/systemd/system/
sudo install -m 0644 systemd/satdump-cleanup.service       /etc/systemd/system/
sudo install -m 0644 systemd/satdump-cleanup.timer         /etc/systemd/system/
sudo systemctl daemon-reload
```

### 5) Enable/Start
```bash
sudo systemctl enable --now satdump-goes19.service
sudo systemctl enable --now update-goes-fd-web.timer
sudo systemctl enable --now satdump-cleanup.timer
```

---

## Operations

### Check SatDump is running
```bash
systemctl status satdump-goes19.service --no-pager
sudo tr '\0' ' ' < /proc/$(systemctl show -p MainPID --value satdump-goes19.service)/cmdline ; echo
```

### Publish “latest Full Disk” immediately (one-shot)
```bash
sudo systemctl start update-goes-fd-web.service
cat /var/www/goes/meta.json
ls -l /var/www/goes/latest_*.png
```

### Cleanup immediately (one-shot)
```bash
sudo systemctl start satdump-cleanup.service
tail -n 200 /var/log/satdump_cleanup.log
```

### Change retention window
Edit `/etc/satdump_cleanup.conf`:
```bash
sudo nano /etc/satdump_cleanup.conf
```
Then run a one-shot cleanup to verify:
```bash
sudo systemctl start satdump-cleanup.service
tail -n 200 /var/log/satdump_cleanup.log
```

---

## Safety notes (read once)

- `satdump-cleanup` **deletes directories** under the configured `ROOT`. It only deletes timestamped directories that match SatDump naming patterns and are older than `TOOOLD_DAYS`. Still: double-check `ROOT` before enabling the timer.
- All scripts use `set -euo pipefail` and write explicit logs to reduce silent failures.

---

## Troubleshooting quick hits

### “Input file rtlsdr does not exist!”
That error occurs when SatDump is invoked in a non-`live` mode expecting an input file path. For live RTL-SDR decoding you must use:
```
satdump live goes_hrit GOES-19 --source rtlsdr ...
```

### Publisher picks “old” Full Disk
The publisher chooses the newest directory containing `ANCHOR` (default `product.cbor`). If your Full Disk directories are missing the expected anchor, set:
```
ANCHOR=product.cbor
```
in `update_goes_fd_web.sh` (already default in this release).

---

## File layout in this release

```
.
├── README.md
├── README.pdf
├── scripts/
│   ├── install_wizard.sh
│   ├── run_satdump_goes19.sh
│   ├── update_goes_fd_web.sh
│   └── cleanup_satdump_old.sh
└── systemd/
    ├── satdump-goes19.service
    ├── update-goes-fd-web.service
    ├── update-goes-fd-web.timer
    ├── satdump-cleanup.service
    └── satdump-cleanup.timer
```
