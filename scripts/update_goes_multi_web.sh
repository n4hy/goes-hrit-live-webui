#!/usr/bin/env bash
set -euo pipefail

WEB_ROOT="/var/www/goes"
TRIGGER="$WEB_ROOT/.trigger"
META="$WEB_ROOT/meta.json"

# Candidate Full Disk roots (edit if needed)
CANDIDATES=(
  "GOES-18:/home/pi/sat/GOES-18/IMAGES/GOES-18/Full Disk"
  "GOES-19:/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk"
)

mkdir -p "$WEB_ROOT/current"

pick_newest_dir() {
  local root="$1"
  local line
  line="$(find "$root" -type f -name 'product.cbor' -printf '%T@ %h\n' 2>/dev/null | sort -nr | head -n 1 || true)"
  [[ -z "$line" ]] && { echo ""; return 0; }
  echo "${line#* }"
}

publish_one() {
  local sat="$1"
  local root="$2"
  [[ -d "$root" ]] || return 0

  local newest_dir
  newest_dir="$(pick_newest_dir "$root")"
  [[ -n "$newest_dir" ]] || return 0

  local out="$WEB_ROOT/current/$sat"
  mkdir -p "$out"
  rm -f "$out/"*

  shopt -s nullglob
  cp -f "$newest_dir"/*.png "$out/" 2>/dev/null || true
  cp -f "$newest_dir"/product.cbor "$out/" 2>/dev/null || true
  shopt -u nullglob

  printf '{\n  "satellite": "%s",\n  "timestamp_dir": "%s",\n  "updated_utc": "%s"\n}\n' \
    "$sat" "$(basename "$newest_dir")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$WEB_ROOT/meta_${sat}.json"

  echo "$sat|$(basename "$newest_dir")"
}

updated_any=0
last_sat=""
last_dir=""

for item in "${CANDIDATES[@]}"; do
  sat="${item%%:*}"
  root="${item#*:}"
  res="$(publish_one "$sat" "$root" || true)"
  if [[ -n "$res" ]]; then
    updated_any=1
    last_sat="${res%%|*}"
    last_dir="${res#*|}"
  fi
done

if [[ "$updated_any" -eq 1 ]]; then
  printf '{\n  "satellite": "%s",\n  "timestamp_dir": "%s",\n  "updated_utc": "%s"\n}\n' \
    "$last_sat" "$last_dir" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$META"
  touch "$TRIGGER" || true
fi
