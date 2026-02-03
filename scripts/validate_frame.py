#!/usr/bin/env python3
"""
Validate GOES Full Disk frames for data loss corruption.

Simple rule: if ANY row in the Earth disk region has all identical pixels,
it's data loss. Real satellite imagery always has pixel variation.

Usage: validate_frame.py <image_path>
Exit codes:
  0 = valid frame
  1 = corrupt frame
  2 = error
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Error: PIL and numpy required", file=sys.stderr)
    sys.exit(2)

DISK_MARGIN = 500  # pixels from edge to avoid image border


def validate_frame(image_path: str) -> tuple[bool, str]:
    """
    Check if a frame has data loss.
    
    ANY row with all identical pixels = corrupt. No exceptions.
    """
    try:
        img = Image.open(image_path)
    except Exception as e:
        return False, f"Cannot open image: {e}"

    arr = np.array(img)
    if len(arr.shape) == 3:
        arr = arr[:, :, 0]

    height, width = arr.shape
    margin = min(DISK_MARGIN, height // 10, width // 10)

    # Check each row - ANY identical row = corrupt
    for y in range(margin, height - margin):
        row = arr[y, margin:width - margin]
        if np.std(row) == 0:
            return False, f"Data loss at row {y} (all pixels = {int(row[0])})"

    return True, "Frame OK"


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <image_path>", file=sys.stderr)
        sys.exit(2)

    image_path = sys.argv[1]
    if not Path(image_path).exists():
        print(f"File not found: {image_path}", file=sys.stderr)
        sys.exit(2)

    is_valid, reason = validate_frame(image_path)
    print(f"{'VALID' if is_valid else 'CORRUPT'}: {reason}")
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
