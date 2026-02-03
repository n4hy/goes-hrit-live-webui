#!/usr/bin/env bash
set -euo pipefail

# Generate animated GIF timelapse from GOES Full Disk images
# Usage: make_timelapse_gif.sh <SAT> <BAND> <HOURS> [FRAMES] [--reject-bad]
# 
# When frames are rejected, adjacent valid frames are used to fill gaps,
# maintaining smooth animation and consistent frame count.

SAT="${1:?SAT required (GOES-18 or GOES-19)}"
BAND="${2:?BAND required (e.g. 13)}"
HOURS="${3:-6}"
FRAMES="${4:-24}"
REJECT_BAD=0

for arg in "$@"; do
    [[ "$arg" == "--reject-bad" ]] && REJECT_BAD=1
done

VALIDATE_SCRIPT="/usr/local/bin/validate_frame.py"
ROOT="/home/pi/sat/${SAT}/IMAGES/${SAT}/Full Disk"
OUTROOT="/var/www/goes/timelapse"
mkdir -p "$OUTROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

CUTOFF=$(date -d "${HOURS} hours ago" +%s 2>/dev/null || date -v-${HOURS}H +%s 2>/dev/null || echo 0)

# Find all frames in time window
find "$ROOT" -type f -name "G??_${BAND}_*.png" -print0 2>/dev/null | \
    while IFS= read -r -d '' file; do
        mtime=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo 0)
        if [[ "$mtime" -ge "$CUTOFF" ]]; then
            echo "$mtime $file"
        fi
    done | sort -n > "$TMP/all_with_times.txt" || true

if [[ ! -s "$TMP/all_with_times.txt" ]]; then
    echo "No frames found for $SAT band $BAND in last ${HOURS}h"
    exit 1
fi

# Use Python for smart frame selection with gap filling
python3 << PYEOF
import random
import subprocess
import sys

validate_script = "$VALIDATE_SCRIPT"
reject_bad = $REJECT_BAD
target_frames = $FRAMES

# Read all frames with timestamps
frames = []
with open("$TMP/all_with_times.txt") as f:
    for line in f:
        parts = line.strip().split(' ', 1)
        if len(parts) == 2:
            mtime, path = int(parts[0]), parts[1]
            frames.append({'mtime': mtime, 'path': path, 'valid': None})

if not frames:
    print("No frames found")
    sys.exit(1)

# Validate frames if requested
if reject_bad:
    rejected = 0
    for frame in frames:
        try:
            result = subprocess.run(
                ['python3', validate_script, frame['path']],
                capture_output=True, timeout=30
            )
            frame['valid'] = (result.returncode == 0)
            if not frame['valid']:
                rejected += 1
        except:
            frame['valid'] = False
            rejected += 1
    
    if rejected > 0:
        print(f"Rejected {rejected} corrupt frame(s)")
    
    valid_frames = [f for f in frames if f['valid']]
else:
    valid_frames = frames
    for f in frames:
        f['valid'] = True

if not valid_frames:
    print("No valid frames remaining")
    sys.exit(1)

# Calculate target timestamps (evenly spaced)
min_time = frames[0]['mtime']
max_time = frames[-1]['mtime']
time_span = max_time - min_time

if time_span <= 0 or len(valid_frames) <= target_frames:
    # Not enough frames or no time span - use all valid frames
    selected = [f['path'] for f in valid_frames]
else:
    # Smart selection: for each target slot, find nearest valid frame
    selected = []
    used_indices = set()
    
    for i in range(target_frames):
        # Target timestamp for this slot
        target_time = min_time + (time_span * i / (target_frames - 1)) if target_frames > 1 else min_time
        
        # Find nearest valid frame to target time
        best_idx = None
        best_dist = float('inf')
        
        for idx, frame in enumerate(frames):
            if not frame['valid']:
                continue
            dist = abs(frame['mtime'] - target_time)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        
        if best_idx is not None:
            # If this exact frame already used, try adjacent valid frames
            if best_idx in used_indices:
                # Look for nearby alternatives
                candidates = []
                for offset in [-1, 1, -2, 2, -3, 3]:
                    alt_idx = best_idx + offset
                    if 0 <= alt_idx < len(frames) and frames[alt_idx]['valid'] and alt_idx not in used_indices:
                        candidates.append(alt_idx)
                
                if candidates:
                    # Randomly pick from adjacent valid frames
                    best_idx = random.choice(candidates)
            
            if best_idx not in used_indices:
                used_indices.add(best_idx)
                selected.append(frames[best_idx]['path'])

# Write selected frames
with open("$TMP/selected.txt", 'w') as f:
    for path in selected:
        f.write(path + '\n')

print(f"Selected {len(selected)} frames")
PYEOF

if [[ ! -s "$TMP/selected.txt" ]]; then
    echo "No frames selected"
    exit 1
fi

# Build ffmpeg concat file
while IFS= read -r filepath; do
    echo "file '$filepath'"
    echo "duration 0.1"
done < "$TMP/selected.txt" > "$TMP/concat.txt"

OUTFILE="$OUTROOT/${SAT}_B${BAND}_${HOURS}h.gif"

# Generate GIF
ffmpeg -hide_banner -loglevel warning -y \
    -f concat -safe 0 -i "$TMP/concat.txt" \
    -vf "scale=1024:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
    -loop 0 \
    "$OUTFILE"

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

chmod 664 "$OUTFILE" "$OUTROOT/${SAT}_B${BAND}_${HOURS}h.json" 2>/dev/null || true

echo "Generated: $OUTFILE ($FRAME_COUNT frames)"
