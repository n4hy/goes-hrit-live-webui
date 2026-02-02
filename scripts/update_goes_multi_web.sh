#!/usr/bin/env bash
set -euo pipefail

WEB_ROOT="/var/www/goes"
TRIGGER="$WEB_ROOT/.trigger"
META="$WEB_ROOT/meta.json"
VALIDATION_CONFIG="$WEB_ROOT/.validation_enabled"
# Validator script location (check /usr/local/bin first, then script dir)
if [[ -f "/usr/local/bin/validate_hrit_image.py" ]]; then
  VALIDATOR="/usr/local/bin/validate_hrit_image.py"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  VALIDATOR="$SCRIPT_DIR/validate_hrit_image.py"
fi

# Read validation setting from config file (default: enabled)
get_validation_enabled() {
  if [[ -f "$VALIDATION_CONFIG" ]]; then
    local val
    val="$(cat "$VALIDATION_CONFIG" 2>/dev/null | tr '[:upper:]' '[:lower:]')"
    case "$val" in
      1|true|yes|enabled) echo 1 ;;
      *) echo 0 ;;
    esac
  else
    echo 1  # Default to enabled
  fi
}

VALIDATE_IMAGES="$(get_validation_enabled)"

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

pick_newest_dir() {
  local root="$1"
  local line
  line="$(find "$root" -type f -name 'product.cbor' -printf '%T@ %h\n' 2>/dev/null | sort -nr | head -n 1 || true)"
  [[ -z "$line" ]] && { echo ""; return 0; }
  echo "${line#* }"
}

# Convert sector name to safe directory name
safe_sector_name() {
  echo "$1" | tr ' ' '_'
}

validate_image() {
  # Validate a single image for black bar corruption
  # Returns 0 if valid, 1 if corrupted
  local img="$1"
  if [[ "$VALIDATE_IMAGES" -eq 1 ]] && [[ -x "$(command -v python3)" ]] && [[ -f "$VALIDATOR" ]]; then
    python3 "$VALIDATOR" "$img" --threshold 0.02 --min-bar-height 8 >/dev/null 2>&1
    return $?
  fi
  return 0  # Skip validation if disabled or validator not available
}

publish_one() {
  local sat="$1"
  local sector="$2"
  local root="$3"
  [[ -d "$root" ]] || return 0

  local newest_dir
  newest_dir="$(pick_newest_dir "$root")"
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
    if validate_image "$png"; then
      cp -f "$png" "$out/" 2>/dev/null && ((copied++)) || true
    else
      ((rejected++)) || true
    fi
  done
  cp -f "$newest_dir"/product.cbor "$out/" 2>/dev/null || true
  shopt -u nullglob

  # Only publish if at least one valid image was copied
  if [[ "$copied" -eq 0 ]]; then
    rm -rf "$out"
    return 0
  fi

  printf '{\n  "satellite": "%s",\n  "sector": "%s",\n  "timestamp_dir": "%s",\n  "updated_utc": "%s",\n  "images_copied": %d,\n  "images_rejected": %d\n}\n' \
    "$sat" "$sector" "$(basename "$newest_dir")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$copied" "$rejected" \
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
