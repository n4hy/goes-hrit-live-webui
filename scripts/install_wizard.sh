#!/usr/bin/env bash
set -euo pipefail

# SatDump GOES-19 HRIT installer / configuration wizard.
# Goal: keep the user entirely on-screen; prompt each step; print warnings before danger.

BOLD="$(tput bold 2>/dev/null || true)"
DIM="$(tput dim 2>/dev/null || true)"
RED="$(tput setaf 1 2>/dev/null || true)"
YEL="$(tput setaf 3 2>/dev/null || true)"
GRN="$(tput setaf 2 2>/dev/null || true)"
RST="$(tput sgr0 2>/dev/null || true)"

say() { printf "%s\n" "$*"; }
hdr() { say ""; say "${BOLD}$*${RST}"; }
warn() { say "${YEL}WARNING:${RST} $*"; }
err() { say "${RED}ERROR:${RST} $*"; }
ok() { say "${GRN}OK:${RST} $*"; }

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    err "Run as root: sudo $0"
    exit 1
  fi
}

prompt_default() {
  local prompt="$1" default="$2" var
  read -r -p "${prompt} [${default}]: " var || true
  if [[ -z "${var}" ]]; then
    var="${default}"
  fi
  printf "%s" "${var}"
}

confirm() {
  local prompt="$1" ans
  read -r -p "${prompt} [y/N]: " ans || true
  [[ "${ans}" =~ ^[Yy]$ ]]
}

write_file_root() {
  local path="$1" mode="$2"
  shift 2
  local tmp
  tmp="$(mktemp)"
  cat >"${tmp}"
  install -m "${mode}" "${tmp}" "${path}"
  rm -f "${tmp}"
}

main() {
  need_root

  hdr "SatDump GOES-19 HRIT – Installer Wizard"
  say "${DIM}This wizard installs scripts, writes configs, installs systemd units, and enables timers.${RST}"
  say "${DIM}You can abort any time with Ctrl-C.${RST}"

  hdr "Step 1 – Confirm SatDump binary"
  local satdump_default="/home/pi/SatDump/build/satdump"
  local SATDUMP_BIN
  SATDUMP_BIN="$(prompt_default "SatDump binary path" "${satdump_default}")"
  if [[ ! -x "${SATDUMP_BIN}" ]]; then
    err "Not executable: ${SATDUMP_BIN}"
    exit 1
  fi
  ok "Using SatDump: ${SATDUMP_BIN}"

  hdr "Step 2 – Confirm RTL-SDR live parameters"
  local FREQ SR GAIN
  FREQ="$(prompt_default "Downlink frequency (Hz or scientific), e.g. 1694.1e6" "1694.1e6")"
  SR="$(prompt_default "Sample rate, e.g. 2.048e6" "2.048e6")"
  GAIN="$(prompt_default "RTL-SDR gain (dB), e.g. 48" "48")"
  ok "Live params: frequency=${FREQ} samplerate=${SR} gain=${GAIN}"

  hdr "Step 3 – Output root for SatDump"
  say "This is where SatDump will create GOES-19 directories."
  local OUTROOT
  OUTROOT="$(prompt_default "Output directory" "/home/pi/sat/goes19")"

  if [[ "${OUTROOT}" == "/" || "${OUTROOT}" == "/home" || "${OUTROOT}" == "/home/pi" ]]; then
    warn "Output root looks too broad (${OUTROOT}). This is usually a mistake."
    if ! confirm "Continue anyway?"; then
      err "Aborting on user request."
      exit 1
    fi
  fi

  mkdir -p "${OUTROOT}"
  ok "Output directory exists: ${OUTROOT}"

  hdr "Step 4 – Full Disk source directory for web publisher"
  say "Publisher will scan for newest Full Disk directory under:"
  local FDROOT
  FDROOT="$(prompt_default "Full Disk root" "${OUTROOT}/IMAGES/GOES-19/Full Disk")"
  ok "Full Disk root: ${FDROOT}"

  hdr "Step 5 – Web publish directory"
  local WEBROOT
  WEBROOT="$(prompt_default "Web root (served by your web server)" "/var/www/goes")"
  mkdir -p "${WEBROOT}"
  chown www-data:www-data "${WEBROOT}" || true
  ok "Web root ready: ${WEBROOT}"

  hdr "Step 6 – Retention policy (TOOOLD_DAYS)"
  warn "Cleanup deletes old directories under a root path. Verify carefully."
  local TOOOLD
  TOOOLD="$(prompt_default "Days to retain (TOOOLD_DAYS)" "7")"
  local CLEANROOT
  CLEANROOT="$(prompt_default "Cleanup ROOT (directory containing satdump outputs)" "/home/pi/sat")"

  if [[ "${CLEANROOT}" == "/" || "${CLEANROOT}" == "/home" || "${CLEANROOT}" == "/home/pi" ]]; then
    warn "Cleanup ROOT looks dangerously broad (${CLEANROOT}). Deletion could be catastrophic."
    if ! confirm "Continue anyway?"; then
      err "Aborting on user request."
      exit 1
    fi
  fi
  ok "Retention config: TOOOLD_DAYS=${TOOOLD} ROOT=${CLEANROOT}"

  hdr "Step 7 – Install scripts into /usr/local/bin"
  say "This will overwrite existing scripts with the same names."
  if ! confirm "Proceed with script installation?"; then
    err "Aborting on user request."
    exit 1
  fi
  install -d -m 0755 /usr/local/bin
  # Scripts are expected to be alongside this wizard in /usr/local/bin already OR run from repo.
  # If running from repo, we try to locate the scripts directory.
  local SELF_DIR
  SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
  local SRC_DIR="${SELF_DIR}"
  if [[ -d "${SELF_DIR}/scripts" ]]; then
    SRC_DIR="${SELF_DIR}/scripts"
  fi

  for f in run_satdump_goes19.sh update_goes_fd_web.sh cleanup_satdump_old.sh install_wizard.sh; do
    if [[ -f "${SRC_DIR}/${f}" ]]; then
      install -m 0755 "${SRC_DIR}/${f}" "/usr/local/bin/${f}"
    elif [[ -f "${SELF_DIR}/${f}" ]]; then
      install -m 0755 "${SELF_DIR}/${f}" "/usr/local/bin/${f}"
    else
      err "Missing script: ${f} (expected in ${SRC_DIR} or ${SELF_DIR})"
      exit 1
    fi
  done
  ok "Scripts installed to /usr/local/bin"

  hdr "Step 8 – Write configuration files in /etc"
  write_file_root /etc/satdump_cleanup.conf 0644 <<EOF
# Days to retain SatDump data
TOOOLD_DAYS=${TOOOLD}
# Root of SatDump output (directory that contains goes19/, etc.)
ROOT=${CLEANROOT}
EOF
  ok "Wrote /etc/satdump_cleanup.conf"

  if [[ ! -f /etc/goes_fd_views.conf ]]; then
    write_file_root /etc/goes_fd_views.conf 0644 <<'EOF'
latest_false_color.png=abi_rgb_GEO_False_Color.png
latest_clean_ir.png=abi_rgb_Clean_Longwave_IR_Window_Band.png
latest_longwave_ir.png=abi_rgb_Infrared_Longwave_Window_Band.png
latest_wv_upper.png=abi_rgb_Upper-Level_Tropospheric_Water_Vapor.png
EOF
    ok "Created /etc/goes_fd_views.conf"
  else
    ok "Keeping existing /etc/goes_fd_views.conf"
  fi

  hdr "Step 9 – Install systemd units"
  say "This will (re)write unit files in /etc/systemd/system."
  if ! confirm "Proceed with systemd installation?"; then
    err "Aborting on user request."
    exit 1
  fi

  install -d -m 0755 /etc/systemd/system

  write_file_root /etc/systemd/system/satdump-goes19.service 0644 <<EOF
[Unit]
Description=SatDump GOES-19 HRIT (live, rtl-sdr)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
Environment=SATDUMP_BIN=${SATDUMP_BIN}
Environment=FREQ=${FREQ}
Environment=SR=${SR}
Environment=GAIN=${GAIN}
Environment=OUTROOT=${OUTROOT}
ExecStart=/usr/local/bin/run_satdump_goes19.sh
Restart=always
RestartSec=3
Nice=-5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

  write_file_root /etc/systemd/system/update-goes-fd-web.service 0644 <<EOF
[Unit]
Description=Publish latest GOES-19 Full Disk images for web UI

[Service]
Type=oneshot
User=root
Group=root
Environment=SATDUMP_FD_ROOT=${FDROOT}
Environment=WEB_ROOT=${WEBROOT}
ExecStart=/usr/local/bin/update_goes_fd_web.sh
EOF

  write_file_root /etc/systemd/system/update-goes-fd-web.timer 0644 <<'EOF'
[Unit]
Description=Run GOES-19 Full Disk web publisher periodically

[Timer]
OnBootSec=90
OnUnitActiveSec=60
Persistent=true

[Install]
WantedBy=timers.target
EOF

  write_file_root /etc/systemd/system/satdump-cleanup.service 0644 <<'EOF'
[Unit]
Description=Cleanup SatDump output older than TOOOLD_DAYS

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/local/bin/cleanup_satdump_old.sh
EOF

  write_file_root /etc/systemd/system/satdump-cleanup.timer 0644 <<'EOF'
[Unit]
Description=Run SatDump cleanup daily

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  ok "Installed and reloaded systemd units"

  hdr "Step 10 – Enable and start services/timers"
  warn "SatDump will start capturing immediately and can consume disk. Confirm you want it running now."
  if confirm "Enable and start satdump-goes19.service now?"; then
    systemctl enable --now satdump-goes19.service
    ok "satdump-goes19.service enabled and started"
  else
    warn "satdump-goes19.service not started. You can start it later with:"
    say "  sudo systemctl start satdump-goes19.service"
  fi

  if confirm "Enable and start update-goes-fd-web.timer now?"; then
    systemctl enable --now update-goes-fd-web.timer
    ok "update-goes-fd-web.timer enabled"
    systemctl start update-goes-fd-web.service || true
  else
    warn "Web publisher timer not enabled."
  fi

  if confirm "Enable and start satdump-cleanup.timer now?"; then
    systemctl enable --now satdump-cleanup.timer
    ok "satdump-cleanup.timer enabled"
  else
    warn "Cleanup timer not enabled."
  fi

  hdr "Step 11 – Quick verification commands (copy/paste)"
  cat <<'EOF'
# SatDump service status
systemctl status satdump-goes19.service --no-pager

# Publish latest Full Disk now
sudo systemctl start update-goes-fd-web.service
cat /var/www/goes/meta.json
ls -l /var/www/goes/latest_*.png

# Test cleanup now (dry run is not implemented; it will delete old data)
sudo systemctl start satdump-cleanup.service
tail -n 120 /var/log/satdump_cleanup.log
EOF

  ok "Wizard complete."
}

main "$@"
