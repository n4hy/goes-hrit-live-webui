#!/usr/bin/env bash
set -euo pipefail

# Generate animated GIF timelapse from GOES Full Disk images
# Usage: make_timelapse_gif.sh <SAT> <BAND> <HOURS> [FRAMES] [--reject-bad]
# Example: make_timelapse_gif.sh GOES-19 13 6 24 --reject-bad

SAT="${1:?SAT required (GOES-18 or GOES-19)}"
BAND="${2:?BAND required (e.g. 13)}"
HOURS="${3:-6}"
FRAMES="${4:-24}"
REJECT_BAD=0

# Check for --reject-bad flag
for arg in "$@"; do
    if [[ "$arg" == "--reject-bad" ]]; then
        REJECT_BAD=1
    fi
done

# Minimum file size in bytes (frames smaller than this are likely corrupt)
# Full Disk CH13 is typically 500KB+, Mesoscale smaller
MIN_FILE_SIZE=50000

# Path to image validation script (check /usr/local/bin first, then script dir)
if [[ -f "/usr/local/bin/validate_hrit_image.py" ]]; then
  VALIDATOR="/usr/local/bin/validate_hrit_image.py"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  VALIDATOR="$SCRIPT_DIR/validate_hrit_image.py"
fi

ROOT="/home/pi/sat/${SAT}/IMAGES/${SAT}/Full Disk"
OUTROOT="/var/www/goes/timelapse"
mkdir -p "$OUTROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Calculate cutoff time (HOURS ago)
CUTOFF=$(date -d "${HOURS} hours ago" +%s 2>/dev/null || date -v-${HOURS}H +%s 2>/dev/null || echo 0)

# Find matching images within time window
# Use -print0 and handle spaces in paths properly
find "$ROOT" -type f -name "G??_${BAND}_*.png" -print0 2>/dev/null | \
    while IFS= read -r -d '' file; do
        mtime=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo 0)
        if [[ "$mtime" -ge "$CUTOFF" ]]; then
            echo "$file"
        fi
    done | sort > "$TMP/all.txt" || true

if [[ ! -s "$TMP/all.txt" ]]; then
    echo "No frames found for $SAT band $BAND in last ${HOURS}h under: $ROOT"
    exit 1
fi

# Filter out bad frames if requested
# Uses both file size check AND black bar detection via validation script
if [[ "$REJECT_BAD" -eq 1 ]]; then
    mv "$TMP/all.txt" "$TMP/all_unfiltered.txt"
    REJECTED=0
    REJECTED_SIZE=0
    REJECTED_CORRUPT=0
    while IFS= read -r file; do
        # Check file size (frames smaller than threshold are likely corrupt)
        fsize=$(stat -c %s "$file" 2>/dev/null || stat -f %z "$file" 2>/dev/null || echo 0)
        if [[ "$fsize" -lt "$MIN_FILE_SIZE" ]]; then
            ((REJECTED++)) || true
            ((REJECTED_SIZE++)) || true
            continue
        fi
        # Check for black bar corruption using validation script
        if [[ -f "$VALIDATOR" ]] && command -v python3 &>/dev/null; then
            if ! python3 "$VALIDATOR" "$file" --threshold 0.02 --min-bar-height 8 >/dev/null 2>&1; then
                ((REJECTED++)) || true
                ((REJECTED_CORRUPT++)) || true
                continue
            fi
        fi
        echo "$file"
    done < "$TMP/all_unfiltered.txt" > "$TMP/all.txt"
    if [[ "$REJECTED" -gt 0 ]]; then
        echo "Rejected $REJECTED frame(s) ($REJECTED_SIZE too small, $REJECTED_CORRUPT with black bars)"
    fi
fi

if [[ ! -s "$TMP/all.txt" ]]; then
    echo "No valid frames remaining after filtering"
    exit 1
fi

TOTAL=$(wc -l < "$TMP/all.txt")

# Sample frames evenly if we have more than requested
if [[ "$TOTAL" -gt "$FRAMES" ]]; then
    awk -v total="$TOTAL" -v frames="$FRAMES" '
        BEGIN { step = total / frames }
        NR == 1 || NR >= int((count+1) * step) { print; count++ }
    ' "$TMP/all.txt" | head -n "$FRAMES" > "$TMP/selected.txt"
else
    cp "$TMP/all.txt" "$TMP/selected.txt"
fi

# Build ffmpeg concat file with proper quoting
while IFS= read -r filepath; do
    echo "file '$filepath'"
    echo "duration 0.1"
done < "$TMP/selected.txt" > "$TMP/concat.txt"

OUTFILE="$OUTROOT/${SAT}_B${BAND}_${HOURS}h.gif"

# Generate GIF using ffmpeg
ffmpeg -hide_banner -loglevel warning -y \
    -f concat -safe 0 -i "$TMP/concat.txt" \
    -vf "scale=1024:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
    -loop 0 \
    "$OUTFILE"

# Create JSON metadata file
FRAME_COUNT=$(wc -l < "$TMP/selected.txt")
FIRST_FRAME=$(head -1 "$TMP/selected.txt")
LAST_FRAME=$(tail -1 "$TMP/selected.txt")

cat > "$OUTROOT/${SAT}_B${BAND}_${HOURS}h.json" <<EOF
{
  "satellite": "$SAT",
  "band": "$BAND",
  "hours": $HOURS,
  "frames": $FRAME_COUNT,
  "generated_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "first_frame": "$(basename "$FIRST_FRAME")",
  "last_frame": "$(basename "$LAST_FRAME")"
}
EOF

# Ensure group write permission for www-data
chmod 664 "$OUTFILE" "$OUTROOT/${SAT}_B${BAND}_${HOURS}h.json" 2>/dev/null || true

echo "Generated: $OUTFILE ($FRAME_COUNT frames)"
