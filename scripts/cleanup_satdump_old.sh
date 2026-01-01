#!/usr/bin/env bash
set -euo pipefail

CONF="/etc/satdump_cleanup.conf"
LOG="/var/log/satdump_cleanup.log"

# Defaults if CONF is missing
TOOOLD_DAYS_DEFAULT=7
ROOT_DEFAULT="/home/pi/sat"

log() {
  printf "[%s] %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG}" >/dev/null
}

# Load config (safe parsing: accept only simple NAME=VALUE lines)
TOOOLD_DAYS="${TOOOLD_DAYS_DEFAULT}"
ROOT="${ROOT_DEFAULT}"

if [[ -f "${CONF}" ]]; then
  # shellcheck disable=SC1090
  source "${CONF}"
fi

# Validate TOOOLD_DAYS numeric
if ! [[ "${TOOOLD_DAYS}" =~ ^[0-9]+$ ]]; then
  log "ERROR: TOOOLD_DAYS is not an integer: ${TOOOLD_DAYS}"
  exit 2
fi

# Safety check for ROOT
case "${ROOT}" in
  ""|"/"|"/home"|"/home/pi")
    log "ERROR: Refusing to run with unsafe ROOT='${ROOT}'"
    exit 2
    ;;
esac

mkdir -p "$(dirname "${LOG}")"
touch "${LOG}"
chmod 0644 "${LOG}"

cutoff_epoch="$(date -u -d "${TOOOLD_DAYS} days ago" +%s)"
log "cleanup start (TOOOLD_DAYS=${TOOOLD_DAYS}, root=${ROOT}, cutoff_epoch=${cutoff_epoch})"

# Delete SatDump timestamp directories older than cutoff.
# We delete only directories that match SatDump timestamp naming: YYYY-MM-DD_HH-MM-SS
# and only if their parsed time is older than cutoff.
shopt -s nullglob

delete_one() {
  local dir="$1"
  log "Deleting ${dir}"
  rm -rf --one-file-system "${dir}"
}

# Find candidate timestamp directories under ROOT
# (Examples: .../Full Disk/2025-12-28_23-30-22)
while IFS= read -r dir; do
  bn="$(basename "${dir}")"
  if [[ "${bn}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}$ ]]; then
    # Convert to epoch; if parse fails, skip.
    if epoch="$(date -u -d "${bn//_/ }" +%s 2>/dev/null)"; then
      if (( epoch < cutoff_epoch )); then
        delete_one "${dir}"
      fi
    fi
  fi
done < <(find "${ROOT}" -type d -name '????-??-??_??-??-??' 2>/dev/null | sort)

log "cleanup end"
