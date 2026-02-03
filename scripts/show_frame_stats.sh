#!/usr/bin/env bash
#
# show_frame_stats.sh - Display frame validation statistics
#
# Usage:
#   show_frame_stats.sh [--hours N] [--csv]
#
# Options:
#   --hours N   Show only last N hours (default: 24)
#   --csv       Output raw CSV instead of formatted table
#

STATS_FILE="/var/log/goes/frame_stats.csv"
HOURS=24
RAW_CSV=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours)
      HOURS="$2"
      shift 2
      ;;
    --csv)
      RAW_CSV=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [[ ! -f "$STATS_FILE" ]]; then
  echo "No stats file found: $STATS_FILE"
  exit 1
fi

if [[ "$RAW_CSV" -eq 1 ]]; then
  cat "$STATS_FILE"
  exit 0
fi

echo "=== GOES Frame Validation Statistics ==="
echo ""

# Calculate cutoff time
cutoff=$(date -u -d "$HOURS hours ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)

# Print header
printf "%-20s %-15s %8s %8s %8s  %s\n" "Timestamp" "Source" "Scanned" "Rejected" "Rate" "Note"
printf "%-20s %-15s %8s %8s %8s  %s\n" "--------------------" "---------------" "--------" "--------" "--------" "----"

# Read and filter stats
total_scanned=0
total_rejected=0
count=0

tail -n +2 "$STATS_FILE" | while IFS=, read -r ts source scanned rejected pct note; do
  # Simple filter: show all recent entries
  printf "%-20s %-15s %8s %8s %7s%%  %s\n" "$ts" "$source" "$scanned" "$rejected" "$pct" "$note"
done

echo ""
echo "--- Summary (last $HOURS hours) ---"

# Calculate totals
totals=$(tail -n +2 "$STATS_FILE" | awk -F, '{
  scanned += $3
  rejected += $4
  count++
}
END {
  if (scanned > 0) {
    rate = (rejected / scanned) * 100
  } else {
    rate = 0
  }
  printf "%d %d %d %.1f", count, scanned, rejected, rate
}')

entries=$(echo "$totals" | cut -d' ' -f1)
scanned=$(echo "$totals" | cut -d' ' -f2)
rejected=$(echo "$totals" | cut -d' ' -f3)
rate=$(echo "$totals" | cut -d' ' -f4)

echo "Entries: $entries"
echo "Total scanned: $scanned"
echo "Total rejected: $rejected"
echo "Overall corruption rate: ${rate}%"
echo ""
echo "Higher corruption rates indicate degraded RF signal quality."
echo "Check: antenna alignment, LNA, feedline, interference"
