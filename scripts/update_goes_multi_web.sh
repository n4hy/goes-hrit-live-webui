#!/usr/bin/env bash
set -euo pipefail

WEB_ROOT="/var/www/goes"
TRIGGER="$WEB_ROOT/.trigger"
META="$WEB_ROOT/meta.json"

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
  cp -f "$newest_dir"/*.png "$out/" 2>/dev/null || true
  cp -f "$newest_dir"/product.cbor "$out/" 2>/dev/null || true
  shopt -u nullglob

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
