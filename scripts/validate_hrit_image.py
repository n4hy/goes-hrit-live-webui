#!/usr/bin/env python3
"""
HRIT Image Corruption Detector

Detects "busted" GOES HRIT images with horizontal black bars caused by
Reed-Solomon decode failures and packet loss. Based on the methodology from
"Advanced Systematic Remediation of Image Corruption in Geostationary HRIT
Processing via SatDump and External Validation Architectures".

Key insight: Black bars from data loss span the ENTIRE image width including
Earth's disk, while natural space blackness only appears at image periphery.
We analyze the center 50% of image width to distinguish corruption from space.

Usage:
    validate_hrit_image.py <image_path> [--threshold 0.02] [--min-bar-height 8] [--verbose]
    validate_hrit_image.py --batch <directory> [--move-bad <quarantine_dir>]

Exit codes:
    0 = Image is valid (or --batch mode completed)
    1 = Image is corrupted (black bars detected)
    2 = Image file error (can't open, truncated, etc.)
"""

import argparse
import sys
import os
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def check_dependencies():
    """Check if required dependencies are available."""
    if not HAS_DEPS:
        print("ERROR: Required dependencies not installed.", file=sys.stderr)
        print("Install with: pip3 install pillow numpy", file=sys.stderr)
        sys.exit(2)


def verify_file_integrity(file_path: Path) -> bool:
    """
    Quick check for file header integrity.
    Returns True if file can be opened and has valid structure.
    """
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def detect_black_bars(
    file_path: Path,
    threshold: float = 0.02,
    min_bar_height: int = 8,
    center_fraction: float = 0.5,
    verbose: bool = False
) -> dict:
    """
    Detect horizontal black bars indicative of HRIT data corruption.

    Algorithm:
    1. Load image as grayscale
    2. Crop to center 50% of width (excludes space at edges)
    3. Find rows where ALL pixels are exactly 0 (black)
    4. Group consecutive black rows into "bars"
    5. If bars exist with height >= min_bar_height, image is corrupted

    Args:
        file_path: Path to PNG image
        threshold: Max fraction of image height that can be black bars (0.02 = 2%)
        min_bar_height: Minimum consecutive black rows to count as a "bar"
        center_fraction: Fraction of image width to analyze (0.5 = center 50%)
        verbose: Print detailed analysis

    Returns:
        dict with keys:
            valid: bool - True if image passes validation
            reason: str - Description of result
            black_bar_ratio: float - Fraction of image height that is black bars
            bar_count: int - Number of distinct black bars detected
            bar_heights: list - Heights of each detected bar
            total_black_rows: int - Total black rows in center crop
    """
    result = {
        'valid': False,
        'reason': 'Unknown error',
        'black_bar_ratio': 0.0,
        'bar_count': 0,
        'bar_heights': [],
        'total_black_rows': 0,
        'image_height': 0,
        'image_width': 0
    }

    try:
        # Load and convert to grayscale
        with Image.open(file_path) as img:
            # Get dimensions
            width, height = img.size
            result['image_width'] = width
            result['image_height'] = height

            # Convert to grayscale numpy array
            gray = np.array(img.convert('L'), dtype=np.uint8)

    except Exception as e:
        result['reason'] = f'Failed to load image: {e}'
        return result

    # Crop to center portion (excludes space at image edges)
    margin = int(width * (1 - center_fraction) / 2)
    center_crop = gray[:, margin:width - margin]

    if verbose:
        print(f"  Image size: {width}x{height}")
        print(f"  Analyzing center {int(center_fraction*100)}%: columns {margin} to {width-margin}")

    # Find rows where ALL pixels in center crop are exactly 0
    # This is the key indicator of HRIT packet loss (black padding)
    row_is_black = np.all(center_crop == 0, axis=1)
    black_row_indices = np.where(row_is_black)[0]
    result['total_black_rows'] = len(black_row_indices)

    if len(black_row_indices) == 0:
        result['valid'] = True
        result['reason'] = 'No black bars detected'
        return result

    # Group consecutive black rows into bars
    bars = []
    if len(black_row_indices) > 0:
        bar_start = black_row_indices[0]
        bar_end = black_row_indices[0]

        for i in range(1, len(black_row_indices)):
            if black_row_indices[i] == bar_end + 1:
                # Consecutive row, extend current bar
                bar_end = black_row_indices[i]
            else:
                # Gap detected, save current bar if tall enough
                bar_height = bar_end - bar_start + 1
                if bar_height >= min_bar_height:
                    bars.append({
                        'start': bar_start,
                        'end': bar_end,
                        'height': bar_height
                    })
                # Start new bar
                bar_start = black_row_indices[i]
                bar_end = black_row_indices[i]

        # Don't forget the last bar
        bar_height = bar_end - bar_start + 1
        if bar_height >= min_bar_height:
            bars.append({
                'start': bar_start,
                'end': bar_end,
                'height': bar_height
            })

    result['bar_count'] = len(bars)
    result['bar_heights'] = [b['height'] for b in bars]

    # Calculate total black bar pixels as fraction of image height
    total_bar_height = sum(b['height'] for b in bars)
    result['black_bar_ratio'] = total_bar_height / height

    if verbose:
        print(f"  Total black rows in center: {result['total_black_rows']}")
        print(f"  Detected bars (height >= {min_bar_height}): {len(bars)}")
        for i, bar in enumerate(bars):
            print(f"    Bar {i+1}: rows {bar['start']}-{bar['end']} (height={bar['height']})")
        print(f"  Black bar ratio: {result['black_bar_ratio']:.4f} (threshold: {threshold})")

    # Determine validity
    if len(bars) == 0:
        result['valid'] = True
        result['reason'] = 'No significant black bars detected'
    elif result['black_bar_ratio'] > threshold:
        result['valid'] = False
        result['reason'] = f"Black bar ratio {result['black_bar_ratio']:.2%} exceeds threshold {threshold:.2%}"
    else:
        # Has bars but below threshold - borderline, still flag as invalid
        # because even small black bars indicate data loss
        result['valid'] = False
        result['reason'] = f"Detected {len(bars)} black bar(s) totaling {total_bar_height} rows"

    return result


def validate_image(
    file_path: Path,
    threshold: float = 0.02,
    min_bar_height: int = 8,
    verbose: bool = False
) -> tuple[bool, str]:
    """
    Complete validation of an HRIT image.

    Returns:
        (is_valid, reason) tuple
    """
    # First check file integrity
    if not verify_file_integrity(file_path):
        return False, "File integrity check failed (truncated or corrupt header)"

    # Then check for black bars
    result = detect_black_bars(
        file_path,
        threshold=threshold,
        min_bar_height=min_bar_height,
        verbose=verbose
    )

    return result['valid'], result['reason']


def validate_directory(
    directory: Path,
    pattern: str = "*.png",
    threshold: float = 0.02,
    min_bar_height: int = 8,
    quarantine_dir: Path = None,
    verbose: bool = False
) -> dict:
    """
    Validate all images in a directory.

    Args:
        directory: Path to scan
        pattern: Glob pattern for images
        threshold: Black bar threshold
        min_bar_height: Minimum bar height
        quarantine_dir: If set, move bad images here instead of just reporting
        verbose: Print details for each image

    Returns:
        dict with validation statistics
    """
    import shutil

    stats = {
        'total': 0,
        'valid': 0,
        'corrupted': 0,
        'errors': 0,
        'quarantined': [],
        'corrupted_files': [],
        'error_files': []
    }

    if quarantine_dir:
        quarantine_dir.mkdir(parents=True, exist_ok=True)

    for img_path in sorted(directory.glob(pattern)):
        if not img_path.is_file():
            continue

        stats['total'] += 1

        if verbose:
            print(f"\nValidating: {img_path.name}")

        is_valid, reason = validate_image(
            img_path,
            threshold=threshold,
            min_bar_height=min_bar_height,
            verbose=verbose
        )

        if is_valid:
            stats['valid'] += 1
            if verbose:
                print(f"  VALID: {reason}")
        elif "integrity" in reason.lower() or "failed to load" in reason.lower():
            stats['errors'] += 1
            stats['error_files'].append(str(img_path))
            if verbose:
                print(f"  ERROR: {reason}")
        else:
            stats['corrupted'] += 1
            stats['corrupted_files'].append(str(img_path))
            if verbose:
                print(f"  CORRUPTED: {reason}")

            if quarantine_dir:
                dest = quarantine_dir / img_path.name
                shutil.move(str(img_path), str(dest))
                stats['quarantined'].append(str(dest))
                if verbose:
                    print(f"  -> Moved to quarantine: {dest}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Detect corrupted HRIT satellite images with black bars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check single image
  %(prog)s /path/to/image.png

  # Check with verbose output
  %(prog)s /path/to/image.png --verbose

  # Batch check directory
  %(prog)s --batch /path/to/images/

  # Batch check and quarantine bad images
  %(prog)s --batch /path/to/images/ --move-bad /path/to/quarantine/

  # Adjust sensitivity (stricter)
  %(prog)s /path/to/image.png --threshold 0.01 --min-bar-height 4
"""
    )

    parser.add_argument('image', nargs='?', help='Path to image file to validate')
    parser.add_argument('--batch', metavar='DIR', help='Validate all PNGs in directory')
    parser.add_argument('--move-bad', metavar='DIR', help='Move corrupted images to this directory')
    parser.add_argument('--threshold', type=float, default=0.02,
                        help='Max black bar ratio before rejection (default: 0.02 = 2%%)')
    parser.add_argument('--min-bar-height', type=int, default=8,
                        help='Minimum consecutive black rows to count as bar (default: 8)')
    parser.add_argument('--pattern', default='*.png',
                        help='Glob pattern for batch mode (default: *.png)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print detailed analysis')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')

    args = parser.parse_args()

    check_dependencies()

    # Batch mode
    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"ERROR: Not a directory: {args.batch}", file=sys.stderr)
            sys.exit(2)

        quarantine = Path(args.move_bad) if args.move_bad else None

        stats = validate_directory(
            batch_dir,
            pattern=args.pattern,
            threshold=args.threshold,
            min_bar_height=args.min_bar_height,
            quarantine_dir=quarantine,
            verbose=args.verbose
        )

        if args.json:
            import json
            print(json.dumps(stats, indent=2))
        else:
            print(f"\n{'='*50}")
            print(f"Validation Summary for: {batch_dir}")
            print(f"{'='*50}")
            print(f"Total images:  {stats['total']}")
            print(f"Valid:         {stats['valid']}")
            print(f"Corrupted:     {stats['corrupted']}")
            print(f"Errors:        {stats['errors']}")
            if quarantine:
                print(f"Quarantined:   {len(stats['quarantined'])}")

        sys.exit(0)

    # Single file mode
    if not args.image:
        parser.print_help()
        sys.exit(2)

    img_path = Path(args.image)
    if not img_path.is_file():
        print(f"ERROR: File not found: {args.image}", file=sys.stderr)
        sys.exit(2)

    is_valid, reason = validate_image(
        img_path,
        threshold=args.threshold,
        min_bar_height=args.min_bar_height,
        verbose=args.verbose
    )

    if args.json:
        import json
        result = detect_black_bars(
            img_path,
            threshold=args.threshold,
            min_bar_height=args.min_bar_height
        )
        result['file'] = str(img_path)
        print(json.dumps(result, indent=2))
    else:
        status = "VALID" if is_valid else "CORRUPTED"
        print(f"{status}: {img_path.name} - {reason}")

    sys.exit(0 if is_valid else 1)


if __name__ == '__main__':
    main()
