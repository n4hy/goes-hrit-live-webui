#!/usr/bin/env bash
set -euo pipefail

WEB_ROOT="/var/www/goes"
TRIGGER="$WEB_ROOT/.trigger"
META="$WEB_ROOT/meta.json"
VALIDATE_SCRIPT="/usr/local/bin/validate_frame.py"
STATS_SCRIPT="/usr/local/bin/log_frame_stats.sh"
LOG_DIR="/var/log/goes"
REJECT_LOG="$LOG_DIR/rejected_frames.log"
PUBLISH_STATS="$LOG_DIR/publish_stats.tmp"

# Candidate roots for Full Disk and Mesoscale (edit if needed)
CANDIDATES=(
  "GOES-18:Full Disk:/home/pi/sat/GOES-18/IMAGES/GOES-18/Full Disk"
  "GOES-19:Full Disk:/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk"
  "GOES-18:Mesoscale 1:/home/pi/sat/GOES-18/IMAGES/GOES-18/Mesoscale 1"
  "GOES-19:Mesoscale 1:/home/pi/sat/GOES-19/IMAGES/GOES-19/Mesoscale 1"
  "GOES-18:Mesoscale 2:/home/pi/sat/GOES-18/IMAGES/GOES-18/Mesoscale 2"
  "GOES-19:Mesoscale 2:/home/pi/sat/GOES-19/IMAGES/GOES-19/Mesoscale 2"
)

mkdir -p "$WEB_ROOT/current"
mkdir -p "$LOG_DIR" 2>/dev/null || true

# Accumulated stats for this run
total_published=0
total_rejected=0

# Load accumulated hourly stats
load_hourly_stats() {
  if [[ -f "$PUBLISH_STATS" ]]; then
    source "$PUBLISH_STATS"
  else
    HOURLY_PUBLISHED=0
    HOURLY_REJECTED=0
    HOURLY_START=$(date +%H)
  fi
}

# Save accumulated hourly stats
save_hourly_stats() {
  local current_hour=$(date +%H)

  # If hour changed, log stats and reset
  if [[ "$current_hour" != "$HOURLY_START" && -x "$STATS_SCRIPT" ]]; then
    local total=$((HOURLY_PUBLISHED + HOURLY_REJECTED))
    if [[ "$total" -gt 0 ]]; then
      "$STATS_SCRIPT" "publish-hourly" "$total" "$HOURLY_REJECTED" "hour=$HOURLY_START" || true
    fi
    HOURLY_PUBLISHED=0
    HOURLY_REJECTED=0
    HOURLY_START=$current_hour
  fi

  # Update with this run's counts
  HOURLY_PUBLISHED=$((HOURLY_PUBLISHED + total_published))
  HOURLY_REJECTED=$((HOURLY_REJECTED + total_rejected))

  # Save to file
  cat > "$PUBLISH_STATS" <<EOF
HOURLY_PUBLISHED=$HOURLY_PUBLISHED
HOURLY_REJECTED=$HOURLY_REJECTED
HOURLY_START=$HOURLY_START
EOF
}

load_hourly_stats

# Check if a frame is valid (no black bars)
is_valid_frame() {
  local png="$1"
  # Only validate Full Disk frames (they have black bar issues)
  # Mesoscale frames are smaller and don't have this problem
  if [[ "$png" != *"Full"* && "$png" != *"full"* ]]; then
    return 0
  fi
  # Skip if validator not available
  [[ -x "$VALIDATE_SCRIPT" ]] || return 0
  # Run validation - returns 0 for valid, 1 for corrupt
  python3 "$VALIDATE_SCRIPT" "$png" >/dev/null 2>&1
}

# Log rejected frame
log_rejection() {
  local png="$1"
  local reason="$2"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) REJECTED: $png - $reason" >> "$REJECT_LOG" 2>/dev/null || true
}

pick_newest_dir() {
  local root="$1"
  local line
  line="$(find "$root" -type f -name 'product.cbor' -printf '%T@ %h\n' 2>/dev/null | sort -nr | head -n 1 || true)"
  [[ -z "$line" ]] && { echo ""; return 0; }
  echo "${line#* }"
}

# Pick newest directory that has at least one valid frame
pick_newest_valid_dir() {
  local root="$1"
  local sector="$2"
  local dirs
  dirs="$(find "$root" -type f -name 'product.cbor' -printf '%T@ %h\n' 2>/dev/null | sort -nr | head -n 10 || true)"
  [[ -z "$dirs" ]] && { echo ""; return 0; }

  # For non-Full-Disk sectors, just return newest
  if [[ "$sector" != "Full Disk" ]]; then
    echo "$dirs" | head -n 1 | cut -d' ' -f2-
    return 0
  fi

  # For Full Disk, find first directory with valid frames
  while IFS= read -r line; do
    local dir="${line#* }"
    [[ -z "$dir" ]] && continue

    # Check if any PNG in this directory is valid
    local has_valid=0
    for png in "$dir"/*.png; do
      [[ -f "$png" ]] || continue
      if is_valid_frame "$png"; then
        has_valid=1
        break
      fi
    done

    if [[ "$has_valid" -eq 1 ]]; then
      echo "$dir"
      return 0
    else
      log_rejection "$dir" "All frames corrupt, skipping directory"
    fi
  done <<< "$dirs"

  # Fallback to newest if all are bad
  echo "$dirs" | head -n 1 | cut -d' ' -f2-
}

# Convert sector name to safe directory name
safe_sector_name() {
  echo "$1" | tr ' ' '_'
}

publish_one() {
  local sat="$1"
  local sector="$2"
  local root="$3"
  [[ -d "$root" ]] || return 0

  local newest_dir
  newest_dir="$(pick_newest_valid_dir "$root" "$sector")"
  [[ -n "$newest_dir" ]] || return 0

  local safe_sector
  safe_sector="$(safe_sector_name "$sector")"

  local out="$WEB_ROOT/current/$sat/$safe_sector"
  mkdir -p "$out"
  rm -f "$out/"*

  shopt -s nullglob
  local copied=0
  local rejected=0
  for png in "$newest_dir"/*.png; do
    [[ -f "$png" ]] || continue
    if is_valid_frame "$png"; then
      cp -f "$png" "$out/" 2>/dev/null && copied=$((copied + 1)) || true
    else
      log_rejection "$png" "Black band corruption"
      rejected=$((rejected + 1))
    fi
  done
  cp -f "$newest_dir"/product.cbor "$out/" 2>/dev/null || true
  shopt -u nullglob

  # Update global stats
  total_published=$((total_published + copied))
  total_rejected=$((total_rejected + rejected))

  # Log if we rejected any frames
  if [[ "$rejected" -gt 0 ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $sat/$sector: Published $copied frames, rejected $rejected" >> "$REJECT_LOG" 2>/dev/null || true
  fi

  printf '{\n  "satellite": "%s",\n  "sector": "%s",\n  "timestamp_dir": "%s",\n  "updated_utc": "%s"\n}\n' \
    "$sat" "$sector" "$(basename "$newest_dir")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$WEB_ROOT/meta_${sat}_${safe_sector}.json"

  echo "$sat|$sector|$(basename "$newest_dir")"
}

updated_any=0
last_sat=""
last_sector=""
last_dir=""

for item in "${CANDIDATES[@]}"; do
  sat="${item%%:*}"
  rest="${item#*:}"
  sector="${rest%%:*}"
  root="${rest#*:}"

  res="$(publish_one "$sat" "$sector" "$root" || true)"
  if [[ -n "$res" ]]; then
    updated_any=1
    last_sat="${res%%|*}"
    rest="${res#*|}"
    last_sector="${rest%%|*}"
    last_dir="${rest#*|}"
  fi
done

if [[ "$updated_any" -eq 1 ]]; then
  printf '{\n  "satellite": "%s",\n  "sector": "%s",\n  "timestamp_dir": "%s",\n  "updated_utc": "%s"\n}\n' \
    "$last_sat" "$last_sector" "$last_dir" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$META"
  touch "$TRIGGER" || true
fi

# Save hourly statistics for RF health monitoring
save_hourly_stats
