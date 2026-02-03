#!/usr/bin/env bash
#
# log_frame_stats.sh - Log frame validation statistics for RF health monitoring
#
# Usage: log_frame_stats.sh <source> <scanned> <rejected> [note]
#
# Example: log_frame_stats.sh "cleanup" 100 15 "6-hour scan"
#
# Statistics are logged to /var/log/goes/frame_stats.csv
#

STATS_FILE="/var/log/goes/frame_stats.csv"

# Create header if file doesn't exist
if [[ ! -f "$STATS_FILE" ]]; then
    echo "timestamp_utc,source,scanned,rejected,corruption_pct,note" > "$STATS_FILE"
fi

SOURCE="${1:-unknown}"
SCANNED="${2:-0}"
REJECTED="${3:-0}"
NOTE="${4:-}"

# Calculate corruption percentage
if [[ "$SCANNED" -gt 0 ]]; then
    CORRUPTION_PCT=$(awk "BEGIN {printf \"%.1f\", ($REJECTED / $SCANNED) * 100}")
else
    CORRUPTION_PCT="0.0"
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Append to CSV
echo "${TIMESTAMP},${SOURCE},${SCANNED},${REJECTED},${CORRUPTION_PCT},\"${NOTE}\"" >> "$STATS_FILE"

# Also output for caller
echo "Logged: scanned=$SCANNED rejected=$REJECTED corruption=${CORRUPTION_PCT}%"
