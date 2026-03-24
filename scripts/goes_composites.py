#!/usr/bin/env python3
"""
GOES ABI False Color Composite Generation

Generates RGB composite images from individual ABI channel images.
Supports:
- Nighttime Microphysics RGB (CH7, CH8, CH13)
- Day Convection RGB (CH2, CH7, CH13)
- Split Window Difference (CH7 - CH13)

Usage:
    from goes_composites import generate_all_composites
    generate_all_composites(channel_paths, output_dir, timestamp)
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def load_channel(path: Path) -> Optional[np.ndarray]:
    """Load a PNG image as a normalized float32 array (0-1 range).

    Args:
        path: Path to the PNG file

    Returns:
        Normalized float32 numpy array, or None if loading fails
    """
    try:
        img = Image.open(path)
        # Convert to grayscale if RGB
        if img.mode == 'RGB' or img.mode == 'RGBA':
            img = img.convert('L')
        elif img.mode != 'L':
            img = img.convert('L')
        arr = np.array(img, dtype=np.float32) / 255.0
        return arr
    except Exception as e:
        logger.error(f"Failed to load channel {path}: {e}")
        return None


def create_nighttime_microphysics(ch7: np.ndarray, ch8: np.ndarray,
                                   ch13: np.ndarray) -> Image.Image:
    """Create Nighttime Microphysics RGB composite.

    This composite highlights fog and low stratus clouds at night by
    exploiting differences in emissivity between water droplets and
    ice crystals at different IR wavelengths.

    Recipe:
        Red:   CH13 - CH7 (3.9 vs 10.3 um difference)
        Green: CH13 - CH8 (6.2 vs 10.3 um difference)
        Blue:  CH13 (10.3 um brightness temperature)

    Args:
        ch7: Clean IR window (3.9 um) as normalized array
        ch8: Upper water vapor (6.19 um) as normalized array
        ch13: Longwave IR (10.3 um) as normalized array

    Returns:
        PIL Image in RGB mode
    """
    # Compute differences and normalize to 0-1 range
    # Add 0.5 offset to center differences around middle gray
    red = np.clip((ch13 - ch7) + 0.5, 0, 1)
    green = np.clip((ch13 - ch8) + 0.5, 0, 1)
    blue = ch13

    # Stack into RGB array
    rgb = np.stack([red, green, blue], axis=-1)
    rgb_uint8 = (rgb * 255).astype(np.uint8)

    return Image.fromarray(rgb_uint8, mode='RGB')


def create_day_convection(ch2: np.ndarray, ch7: np.ndarray,
                          ch13: np.ndarray) -> Image.Image:
    """Create Day Convection RGB composite.

    This composite highlights developing convection by showing the
    difference between shortwave and longwave IR (indicating small
    ice particles at cloud tops) combined with visible reflectance.

    Recipe:
        Red:   CH7 - CH13 (shortwave minus longwave IR)
        Green: CH2 - CH7 (visible minus shortwave IR)
        Blue:  CH2 (visible reflectance)

    Args:
        ch2: Visible (0.64 um) as normalized array
        ch7: Clean IR window (3.9 um) as normalized array
        ch13: Longwave IR (10.3 um) as normalized array

    Returns:
        PIL Image in RGB mode
    """
    # Compute differences and normalize
    red = np.clip((ch7 - ch13) + 0.5, 0, 1)
    green = np.clip((ch2 - ch7) + 0.5, 0, 1)
    blue = ch2

    # Stack into RGB array
    rgb = np.stack([red, green, blue], axis=-1)
    rgb_uint8 = (rgb * 255).astype(np.uint8)

    return Image.fromarray(rgb_uint8, mode='RGB')


def apply_diverging_colormap(data: np.ndarray) -> Image.Image:
    """Apply a blue-white-red diverging colormap to normalized data.

    Args:
        data: Normalized array (0-1 range, 0.5 = neutral)

    Returns:
        PIL Image in RGB mode
    """
    # Create colormap: blue (0) -> white (0.5) -> red (1)
    rgb = np.zeros((*data.shape, 3), dtype=np.float32)

    # Below midpoint: blue to white
    below = data < 0.5
    t = data[below] * 2  # Scale 0-0.5 to 0-1
    rgb[below, 0] = t      # Red increases
    rgb[below, 1] = t      # Green increases
    rgb[below, 2] = 1.0    # Blue stays at 1

    # Above midpoint: white to red
    above = data >= 0.5
    t = (data[above] - 0.5) * 2  # Scale 0.5-1 to 0-1
    rgb[above, 0] = 1.0          # Red stays at 1
    rgb[above, 1] = 1.0 - t      # Green decreases
    rgb[above, 2] = 1.0 - t      # Blue decreases

    rgb_uint8 = (rgb * 255).astype(np.uint8)
    return Image.fromarray(rgb_uint8, mode='RGB')


def create_split_window(ch7: np.ndarray, ch13: np.ndarray) -> Image.Image:
    """Create Split Window Difference composite.

    The difference between 3.9 um and 10.3 um channels reveals
    information about surface type, cloud particle size, and
    atmospheric dust/aerosols.

    Args:
        ch7: Clean IR window (3.9 um) as normalized array
        ch13: Longwave IR (10.3 um) as normalized array

    Returns:
        PIL Image in RGB mode with diverging colormap
    """
    # Compute difference, roughly -1 to +1 range
    diff = ch7 - ch13

    # Normalize to 0-1 with 0.5 as neutral
    normalized = np.clip((diff + 1.0) / 2.0, 0, 1)

    return apply_diverging_colormap(normalized)


def generate_all_composites(channel_paths: Dict[str, Path],
                            output_dir: Path,
                            timestamp: str,
                            enabled: Optional[Dict[str, bool]] = None) -> Dict[str, Path]:
    """Generate all enabled composite images.

    Args:
        channel_paths: Dict mapping channel names to file paths
            Expected keys: CH2, CH7, CH8, CH13
        output_dir: Directory to write composite images
        timestamp: Timestamp string for output filenames (e.g., "20260125T143022Z")
        enabled: Dict of composite name -> enabled flag. If None, all are enabled.

    Returns:
        Dict mapping composite names to output file paths
    """
    if enabled is None:
        enabled = {
            'nighttime_microphysics': True,
            'day_convection': True,
            'split_window': True
        }

    # Load channels
    channels = {}
    for name, path in channel_paths.items():
        arr = load_channel(path)
        if arr is not None:
            channels[name] = arr
        else:
            logger.warning(f"Channel {name} not available at {path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {}

    # Nighttime Microphysics RGB
    if enabled.get('nighttime_microphysics', False):
        if all(ch in channels for ch in ['CH7', 'CH8', 'CH13']):
            try:
                img = create_nighttime_microphysics(
                    channels['CH7'], channels['CH8'], channels['CH13']
                )
                out_path = output_dir / f"composite_nighttime_microphysics_{timestamp}.png"
                img.save(out_path)
                outputs['nighttime_microphysics'] = out_path
                logger.info(f"Generated nighttime microphysics composite: {out_path}")
            except Exception as e:
                logger.error(f"Failed to generate nighttime microphysics: {e}")
        else:
            logger.warning("Missing channels for nighttime microphysics (need CH7, CH8, CH13)")

    # Day Convection RGB
    if enabled.get('day_convection', False):
        if all(ch in channels for ch in ['CH2', 'CH7', 'CH13']):
            try:
                img = create_day_convection(
                    channels['CH2'], channels['CH7'], channels['CH13']
                )
                out_path = output_dir / f"composite_day_convection_{timestamp}.png"
                img.save(out_path)
                outputs['day_convection'] = out_path
                logger.info(f"Generated day convection composite: {out_path}")
            except Exception as e:
                logger.error(f"Failed to generate day convection: {e}")
        else:
            logger.warning("Missing channels for day convection (need CH2, CH7, CH13)")

    # Split Window Difference
    if enabled.get('split_window', False):
        if all(ch in channels for ch in ['CH7', 'CH13']):
            try:
                img = create_split_window(channels['CH7'], channels['CH13'])
                out_path = output_dir / f"composite_split_window_{timestamp}.png"
                img.save(out_path)
                outputs['split_window'] = out_path
                logger.info(f"Generated split window composite: {out_path}")
            except Exception as e:
                logger.error(f"Failed to generate split window: {e}")
        else:
            logger.warning("Missing channels for split window (need CH7, CH13)")

    return outputs


if __name__ == '__main__':
    # Simple test
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 5:
        print("Usage: goes_composites.py <ch2.png> <ch7.png> <ch8.png> <ch13.png>")
        sys.exit(1)

    paths = {
        'CH2': Path(sys.argv[1]),
        'CH7': Path(sys.argv[2]),
        'CH8': Path(sys.argv[3]),
        'CH13': Path(sys.argv[4])
    }

    outputs = generate_all_composites(paths, Path('.'), 'test')
    print(f"Generated: {outputs}")
