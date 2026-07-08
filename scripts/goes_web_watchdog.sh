#!/usr/bin/env bash
set -euo pipefail

LOCKFILE="/run/goes_web_watchdog.lock"
LOGFILE="/var/log/goes_web_watchdog.log"
STATEFILE="/run/goes_web_watchdog.state"   # small state: last_restart_epoch, consecutive_stale

exec 9>"$LOCKFILE"
if ! flock -n 9; then
  exit 0
fi

ts(){ date -u +'%Y-%m-%dT%H:%M:%SZ'; }
log(){ echo "[$(ts)] $*" | tee -a "$LOGFILE"; }
warn(){ log "WARN: $*"; }

CONF="/etc/goes_watchdog.conf"
if [ ! -f "$CONF" ]; then
  log "ERROR: missing config $CONF"
  exit 0
fi
# shellcheck disable=SC1090
source "$CONF"

: "${STALE_SECONDS:?}"
: "${META_STALE_SECONDS:?}"
: "${SATDUMP_SERVICE:?}"
: "${PUBLISHER_SCRIPT:?}"
: "${WEB_ROOT:?}"
: "${WEB_FILES:?}"
: "${SATDUMP_FD_ROOT:?}"
: "${ALERT_TO:?}"

# New hardening knobs (defaults if not present in conf)
RESTART_COOLDOWN_SECONDS="${RESTART_COOLDOWN_SECONDS:-900}"   # never restart SatDump more often than this
STALE_CONSECUTIVE_REQUIRED="${STALE_CONSECUTIVE_REQUIRED:-3}" # require N consecutive stale runs before restart
DISK_MIN_FREE_MB="${DISK_MIN_FREE_MB:-512}"                  # alert if free space low

now_epoch="$(date +%s)"

file_age(){
  local f="$1"
  if [ ! -f "$f" ]; then echo 999999999; return 0; fi
  local m; m="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
  echo $(( now_epoch - m ))
}

meta_age(){
  local mfile="$WEB_ROOT/meta.json"
  if [ ! -f "$mfile" ]; then echo 999999999; return 0; fi
  local u ue
  u="$(jq -r '.updated_utc // empty' "$mfile" 2>/dev/null || true)"
  if [ -z "${u:-}" ] || [ "$u" = "null" ]; then echo 999999999; return 0; fi
  ue="$(date -d "$u" +%s 2>/dev/null || echo 0)"
  if [ "$ue" -le 0 ]; then echo 999999999; return 0; fi
  echo $(( now_epoch - ue ))
}

# return 0 => stale, 1 => fresh
any_web_stale(){
  local found=0
  for b in $WEB_FILES; do
    local f="$WEB_ROOT/$b"
    local a; a="$(file_age "$f")"
    log "age: $f = ${a}s (threshold ${STALE_SECONDS}s)"
    if [ "$a" -gt "$STALE_SECONDS" ]; then found=1; fi
  done
  local ma; ma="$(meta_age)"
  log "age: $WEB_ROOT/meta.json = ${ma}s (threshold ${META_STALE_SECONDS}s)"
  if [ "$ma" -gt "$META_STALE_SECONDS" ]; then found=1; fi
  if [ "$found" -eq 1 ]; then return 0; else return 1; fi
}

publisher_sane(){
  if [ ! -d "$SATDUMP_FD_ROOT" ]; then
    warn "SATDUMP_FD_ROOT missing: $SATDUMP_FD_ROOT"
    return 1
  fi
  # At least one entry present? Use find -print -quit rather than `ls | head`,
  # which trips `set -o pipefail` via SIGPIPE when the directory is large.
  if [ -z "$(find "$SATDUMP_FD_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    warn "no timestamp dirs under: $SATDUMP_FD_ROOT"
    return 1
  fi
  return 0
}

nginx_sane(){
  if ! systemctl is-active --quiet nginx; then
    warn "nginx not active"
    return 1
  fi
  return 0
}

disk_sane(){
  # check WEB_ROOT filesystem free MB
  local avail_kb
  avail_kb="$(df -Pk "$WEB_ROOT" | awk 'NR==2{print $4}' 2>/dev/null || echo 0)"
  local avail_mb=$(( avail_kb / 1024 ))
  log "disk: free on $(df -P "$WEB_ROOT" | awk 'NR==2{print $6}') = ${avail_mb}MB (min ${DISK_MIN_FREE_MB}MB)"
  if [ "$avail_mb" -lt "$DISK_MIN_FREE_MB" ]; then
    return 1
  fi
  return 0
}

run_publisher(){
  log "action: run publisher $PUBLISHER_SCRIPT"
  "$PUBLISHER_SCRIPT" || return 1
  return 0
}

restart_service(){
  local svc="$1"
  log "action: systemctl restart $svc"
  systemctl restart "$svc" || return 1
  return 0
}

send_alert(){
  local subject="$1"; local body="$2"
  log "ALERT: $subject"
  if command -v mail >/dev/null 2>&1; then
    printf '%s\n' "$body" | mail -s "$subject" "$ALERT_TO" || true
  elif command -v sendmail >/dev/null 2>&1; then
    { echo "To: $ALERT_TO"; echo "Subject: $subject"; echo; echo "$body"; } | sendmail -t || true
  else
    warn "no mail/sendmail installed; alert body follows"
    log "$body"
  fi
}

# load state
last_restart=0
consec_stale=0
if [ -f "$STATEFILE" ]; then
  # shellcheck disable=SC1090
  source "$STATEFILE" || true
fi

log "watchdog start"

# sanity checks that should not trigger restarts
publisher_sane || send_alert "GOES watchdog: SatDump output root issue on $(hostname)" \
  "SATDUMP_FD_ROOT=$SATDUMP_FD_ROOT appears missing/empty. Check SatDump output-directory and filesystem."

nginx_sane || send_alert "GOES watchdog: nginx not active on $(hostname)" \
  "nginx service is not active. Run: sudo systemctl status nginx"

if ! disk_sane; then
  send_alert "GOES watchdog: low disk space on $(hostname)" \
    "Low free space on filesystem containing $WEB_ROOT. Free space below ${DISK_MIN_FREE_MB}MB."
fi

# if web fresh -> reset consecutive stale counter, save state, exit
if ! any_web_stale; then
  consec_stale=0
  printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
  log "status: OK (web fresh)"
  log "watchdog end"
  exit 0
fi

# stale
consec_stale=$(( consec_stale + 1 ))
log "status: STALE (consecutive_stale=${consec_stale}/${STALE_CONSECUTIVE_REQUIRED})"

# first attempt: run publisher only
run_publisher || warn "publisher failed"

if ! any_web_stale; then
  consec_stale=0
  printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
  log "recovered: publisher fixed staleness"
  log "watchdog end"
  exit 0
fi

# do not restart SatDump unless stale N times AND cooldown expired
cooldown_left=$(( (last_restart + RESTART_COOLDOWN_SECONDS) - now_epoch ))
if [ "$consec_stale" -lt "$STALE_CONSECUTIVE_REQUIRED" ]; then
  printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
  warn "not restarting SatDump yet (need ${STALE_CONSECUTIVE_REQUIRED} consecutive stale runs)"
  log "watchdog end (still stale)"
  exit 0
fi

if [ "$cooldown_left" -gt 0 ]; then
  printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
  warn "restart cooldown active (${cooldown_left}s remaining); not restarting SatDump"
  log "watchdog end (still stale)"
  exit 0
fi

# restart SatDump (escalation)
restart_service "$SATDUMP_SERVICE" || warn "restart failed"
last_restart="$now_epoch"
sleep 3
run_publisher || warn "publisher failed after restart"

if ! any_web_stale; then
  consec_stale=0
  printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
  log "recovered: restart + publish fixed staleness"
  log "watchdog end"
  exit 0
fi

printf 'last_restart=%s\nconsec_stale=%s\n' "$last_restart" "$consec_stale" >"$STATEFILE"
send_alert "GOES watchdog: web still stale on $(hostname)" \
  "Stale persists after escalation.
consecutive_stale=$consec_stale
cooldown=${RESTART_COOLDOWN_SECONDS}s
WEB_ROOT=$WEB_ROOT
SATDUMP_FD_ROOT=$SATDUMP_FD_ROOT
Check: SatDump output production, publisher mapping, disk space, nginx.
Log: $LOGFILE"

log "watchdog end (still stale)"
exit 0
