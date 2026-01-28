#!/usr/bin/env python3
"""
Validate GOES imagery frames for corruption.
Detects horizontal bands of missing data within the Earth disk.

Usage: validate_frame.py <image_path>
Exit code 0 = valid frame
Exit code 1 = corrupt frame (has black bands)
Exit code 2 = error (file not found, etc.)
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Error: PIL and numpy required", file=sys.stderr)
    sys.exit(2)


def has_black_bands(filepath, black_threshold=5, band_tolerance=0.02):
    """
    Detect horizontal bands of missing data within the Earth disk.

    Strategy:
    1. Find the Earth disk boundaries (where image content exists)
    2. Within those boundaries, detect rows that are almost entirely black
    3. Flag as corrupt if black rows appear inside the Earth region

    Args:
        filepath: Path to image file
        black_threshold: Pixel values below this are considered black
        band_tolerance: Fraction of row width that can be non-black (for noise)

    Returns:
        True if corrupt bands detected, False if clean
    """
    try:
        img = np.array(Image.open(filepath).convert('L'))
    except Exception as e:
        print(f"Cannot open image: {e}", file=sys.stderr)
        return True  # Treat unreadable as corrupt

    height, width = img.shape

    # Calculate mean brightness of each row
    row_means = img.mean(axis=1)

    # Find Earth disk vertical extent
    # Earth rows have significant brightness; space rows are mostly black
    # Use a low threshold to find where Earth content exists
    earth_brightness_threshold = 3  # Very dim rows are likely space or corruption
    content_rows = np.where(row_means > earth_brightness_threshold)[0]

    if len(content_rows) == 0:
        # Entire image is black - definitely corrupt
        return True

    earth_top = content_rows[0]
    earth_bottom = content_rows[-1]

    # Add margin to avoid edge effects (5% of Earth height)
    earth_height = earth_bottom - earth_top
    margin = int(earth_height * 0.05)
    check_top = earth_top + margin
    check_bottom = earth_bottom - margin

    if check_bottom <= check_top:
        # Image too small to analyze meaningfully
        return False

    # Within the Earth region, look for anomalously dark rows
    # These are corruption bands - rows that should have Earth data but are black
    earth_region_means = row_means[check_top:check_bottom]

    # Calculate expected brightness statistics for the Earth region
    # Exclude very dark rows from the baseline calculation
    bright_rows = earth_region_means[earth_region_means > earth_brightness_threshold]

    if len(bright_rows) == 0:
        # No bright rows in Earth region - corrupt
        return True

    median_brightness = np.median(bright_rows)

    # A row is suspiciously dark if it's much darker than the median
    # Missing data bands are typically pure black (near 0)
    dark_row_threshold = min(earth_brightness_threshold, median_brightness * 0.1)

    # Count rows that are suspiciously dark (potential corruption)
    dark_rows_in_earth = np.sum(earth_region_means <= dark_row_threshold)

    # Also check for the specific pattern: rows with center portion black
    # This catches bands that cut through Earth
    center_start = width // 3
    center_end = 2 * width // 3
    center_slice = img[check_top:check_bottom, center_start:center_end]
    center_row_means = center_slice.mean(axis=1)

    # Rows where even the center (which should be Earth) is black
    black_center_rows = np.sum(center_row_means < black_threshold)

    # If more than a few rows have black centers, it's corrupt
    # Allow some tolerance for legitimate dark features
    max_allowed_dark_rows = max(3, int((check_bottom - check_top) * band_tolerance))

    if black_center_rows > max_allowed_dark_rows:
        return True

    if dark_rows_in_earth > max_allowed_dark_rows:
        return True

    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_frame.py <image_path>", file=sys.stderr)
        sys.exit(2)

    filepath = Path(sys.argv[1])

    if not filepath.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(2)

    if has_black_bands(filepath):
        print(f"CORRUPT: {filepath.name}")
        sys.exit(1)
    else:
        print(f"OK: {filepath.name}")
        sys.exit(0)


if __name__ == "__main__":
    main()
