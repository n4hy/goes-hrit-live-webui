#!/usr/bin/env bash
#
# cleanup_bad_frames.sh - Scan and delete GOES frames with black bar corruption
#
# This script finds and deletes bad frames from the GOES image directories.
# Bad frames have horizontal black bands caused by incomplete data reception.
#
# Usage:
#   cleanup_bad_frames.sh [--dry-run] [--hours N] [--verbose]
#
# Options:
#   --dry-run   Show what would be deleted without actually deleting
#   --hours N   Only scan frames from the last N hours (default: all)
#   --verbose   Print detailed output
#
set -euo pipefail

VALIDATE_SCRIPT="/usr/local/bin/validate_frame.py"
STATS_SCRIPT="/usr/local/bin/log_frame_stats.sh"
LOG_DIR="/var/log/goes"
DELETE_LOG="$LOG_DIR/deleted_frames.log"

# Source directories to scan
SOURCE_DIRS=(
  "/home/pi/sat/GOES-18/IMAGES/GOES-18/Full Disk"
  "/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk"
)

DRY_RUN=0
HOURS=""
VERBOSE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --hours)
      HOURS="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Ensure validator exists
if [[ ! -x "$VALIDATE_SCRIPT" ]]; then
  echo "Error: Validator script not found: $VALIDATE_SCRIPT" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" 2>/dev/null || true

log() {
  local msg="$1"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg"
}

log_delete() {
  local file="$1"
  local reason="$2"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) DELETED: $file - $reason" >> "$DELETE_LOG" 2>/dev/null || true
}

total_scanned=0
total_deleted=0
total_errors=0

for source_dir in "${SOURCE_DIRS[@]}"; do
  [[ -d "$source_dir" ]] || continue

  log "Scanning: $source_dir"

  # Build find command
  find_args=("$source_dir" -type f -name "*.png")
  if [[ -n "$HOURS" ]]; then
    find_args+=(-mmin "-$((HOURS * 60))")
  fi

  while IFS= read -r png; do
    [[ -f "$png" ]] || continue
    total_scanned=$((total_scanned + 1))

    # Skip small files (likely incomplete)
    size=$(stat -c%s "$png" 2>/dev/null || echo 0)
    if [[ "$size" -lt 50000 ]]; then
      if [[ "$VERBOSE" -eq 1 ]]; then
        log "SKIP (too small): $png ($size bytes)"
      fi
      continue
    fi

    # Validate the frame
    if ! python3 "$VALIDATE_SCRIPT" "$png" >/dev/null 2>&1; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "WOULD DELETE: $png"
      else
        if rm -f "$png"; then
          log_delete "$png" "Black band corruption"
          if [[ "$VERBOSE" -eq 1 ]]; then
            log "DELETED: $png"
          fi
          total_deleted=$((total_deleted + 1))
        else
          log "ERROR: Failed to delete $png"
          total_errors=$((total_errors + 1))
        fi
      fi
    elif [[ "$VERBOSE" -eq 1 ]]; then
      log "OK: $png"
    fi
  done < <(find "${find_args[@]}" 2>/dev/null || true)
done

log "Cleanup complete: scanned=$total_scanned deleted=$total_deleted errors=$total_errors"

# Log statistics for RF health monitoring
if [[ "$DRY_RUN" -eq 0 && -x "$STATS_SCRIPT" ]]; then
  note="cleanup"
  [[ -n "$HOURS" ]] && note="cleanup-${HOURS}h"
  "$STATS_SCRIPT" "$note" "$total_scanned" "$total_deleted" "errors=$total_errors" || true
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "(Dry run - no files were actually deleted)"
fi
