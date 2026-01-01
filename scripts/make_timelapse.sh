#!/usr/bin/env bash
set -euo pipefail

SAT="${1:?SAT required (GOES-18 or GOES-19)}"
BAND="${2:?BAND required (e.g. 13)}"
WINDOW="${3:-24h}"

ROOT="/home/pi/sat/${SAT}/IMAGES/${SAT}/Full Disk"
OUTROOT="/var/www/goes/videos"
mkdir -p "$OUTROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

find "$ROOT" -type f -name "G??_${BAND}_*.png" 2>/dev/null | sort > "$TMP/list.txt" || true
if [[ ! -s "$TMP/list.txt" ]]; then
  echo "No frames found for $SAT band $BAND under: $ROOT"
  exit 1
fi

awk '{print "file \x27" $0 "\x27"}' "$TMP/list.txt" > "$TMP/concat.txt"

OUT="$OUTROOT/${SAT}_B${BAND}_timelapse.mp4"
ffmpeg -hide_banner -loglevel warning -y \
  -f concat -safe 0 -i "$TMP/concat.txt" \
  -vf "fps=12,format=yuv420p" \
  "$OUT"

echo "Wrote: $OUT"
