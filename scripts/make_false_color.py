#!/usr/bin/env python3
"""
Generate false color composite images from GOES ABI bands.
Usage: make_false_color.py <SAT> <PRESET> [R_BAND] [G_BAND] [B_BAND]

Presets:
  daynight   - CH2 (visible) blended with CH13 (IR) based on sun angle
  fire       - CH7 (shortwave IR) highlights hot spots
  vegetation - CH2 + CH7 combination for vegetation
  sandwich   - CH2 (visible) + CH13 (IR) sandwich blend
  watervapor  - CH8 (6.2um) upper-level water vapor
  geoearthday - GeoColor-style true color (CH1 blue, CH2 red, CH3 veggie)
  custom      - Requires R_BAND, G_BAND, B_BAND arguments
"""

import sys
import json
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Error: PIL and numpy required. Install with: pip3 install pillow numpy")
    sys.exit(1)

SAT_ROOT = "/home/pi/sat/{sat}/IMAGES/{sat}/Full Disk"
WEB_ROOT = Path("/var/www/goes")
OUT_DIR = WEB_ROOT / "falsecolor"

# Required bands per preset
PRESET_BANDS = {
    "daynight":   [2, 13],
    "fire":       [2, 7, 13],
    "vegetation": [2, 7],
    "sandwich":   [2, 13],
    "watervapor":  [8, 13],
    "geoearthday": [1, 2, 3],
}

DISK_MARGIN = 500  # pixels from edge to avoid image border


def validate_band(image_path: Path) -> bool:
    """Check if a band image has data-loss rows (std==0 in disk region)."""
    try:
        img = Image.open(image_path)
    except Exception:
        return False

    arr = np.array(img)
    if len(arr.shape) == 3:
        arr = arr[:, :, 0]

    height, width = arr.shape
    margin = min(DISK_MARGIN, height // 10, width // 10)

    for y in range(margin, height - margin):
        row = arr[y, margin:width - margin]
        if np.std(row) == 0:
            return False

    return True


def find_valid_frame(sat: str, required_bands: list[int]) -> tuple[Path | None, str | None]:
    """Find the newest frame where all required bands exist with matching
    timestamps and pass quality validation."""
    root = Path(SAT_ROOT.format(sat=sat))
    if not root.exists():
        return None, None

    sat_num = sat.replace("GOES-", "")

    for frame_dir in sorted(root.iterdir(), reverse=True):
        if not frame_dir.is_dir() or not (frame_dir / "product.cbor").exists():
            continue

        # Find PNGs to extract timestamp
        pngs = list(frame_dir.glob(f"G{sat_num}_*_*.png"))
        if not pngs:
            continue

        # Extract timestamp from first PNG: G19_2_20260214T120021Z.png
        timestamp = pngs[0].stem.split("_", 2)[2]

        # Check ALL required bands exist with this exact timestamp
        band_files = {}
        all_present = True
        for band in required_bands:
            expected = frame_dir / f"G{sat_num}_{band}_{timestamp}.png"
            if not expected.exists():
                all_present = False
                break
            band_files[band] = expected

        if not all_present:
            continue

        # Validate each band for data quality
        all_valid = True
        for band, path in band_files.items():
            if not validate_band(path):
                print(f"  Skipping {frame_dir.name}: band {band} failed validation", file=sys.stderr)
                all_valid = False
                break

        if all_valid:
            return frame_dir, timestamp

    return None, None


def load_band(frame_dir: Path, sat: str, band: int, timestamp: str) -> np.ndarray | None:
    """Load a band image as grayscale numpy array using exact timestamp."""
    sat_num = sat.replace("GOES-", "")
    path = frame_dir / f"G{sat_num}_{band}_{timestamp}.png"
    if not path.exists():
        return None

    img = Image.open(path).convert('L')
    return np.array(img, dtype=np.float32) / 255.0

def normalize(arr: np.ndarray) -> np.ndarray:
    """Normalize array to 0-1 range."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-6:
        return arr
    return (arr - mn) / (mx - mn)

def make_daynight(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """Day/Night composite: visible by day, IR by night."""
    ch2 = load_band(frame_dir, sat, 2, timestamp)
    ch13 = load_band(frame_dir, sat, 13, timestamp)

    if ch2 is None or ch13 is None:
        raise ValueError("Missing required bands (2, 13)")

    # Simple blend: use visible brightness to weight
    vis_weight = normalize(ch2)
    ir_inv = 1.0 - normalize(ch13)

    r = vis_weight * ch2 + (1 - vis_weight) * ir_inv
    g = vis_weight * ch2 * 0.9 + (1 - vis_weight) * ir_inv * 0.9
    b = vis_weight * ch2 * 0.8 + (1 - vis_weight) * ir_inv

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_fire(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """Fire/Hot Spot: CH7 shortwave IR highlights fires."""
    ch2 = load_band(frame_dir, sat, 2, timestamp)
    ch7 = load_band(frame_dir, sat, 7, timestamp)
    ch13 = load_band(frame_dir, sat, 13, timestamp)

    if ch2 is None or ch7 is None or ch13 is None:
        raise ValueError("Missing required bands (2, 7, 13)")

    ch7_n = normalize(ch7)

    r = np.clip(ch7_n * 1.5, 0, 1)
    g = normalize(ch2) * 0.7
    b = (1.0 - normalize(ch13)) * 0.6

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_vegetation(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """Vegetation composite using visible bands."""
    ch2 = load_band(frame_dir, sat, 2, timestamp)
    ch7 = load_band(frame_dir, sat, 7, timestamp)

    if ch2 is None or ch7 is None:
        raise ValueError("Missing required bands (2, 7)")

    ch2_n = normalize(ch2)
    ch7_n = normalize(ch7)

    r = ch2_n * 0.8
    g = ch7_n * 0.9 + ch2_n * 0.3
    b = ch2_n * 0.5

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_sandwich(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """Sandwich RGB: visible + IR blend."""
    ch2 = load_band(frame_dir, sat, 2, timestamp)
    ch13 = load_band(frame_dir, sat, 13, timestamp)

    if ch2 is None or ch13 is None:
        raise ValueError("Missing required bands (2, 13)")

    ch2_n = normalize(ch2)
    ch13_inv = 1.0 - normalize(ch13)

    r = ch2_n * 0.6 + ch13_inv * 0.4
    g = ch2_n * 0.5 + ch13_inv * 0.5
    b = ch13_inv * 0.8 + ch2_n * 0.2

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_watervapor(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """Water Vapor composite using CH8 upper-level water vapor."""
    ch8 = load_band(frame_dir, sat, 8, timestamp)
    ch13 = load_band(frame_dir, sat, 13, timestamp)

    if ch8 is None or ch13 is None:
        raise ValueError("Missing required bands (8, 13)")

    ch8_n = normalize(ch8)
    ch8_inv = 1.0 - ch8_n

    ch13_inv = 1.0 - normalize(ch13)
    r = ch8_inv * 0.7 + ch13_inv * 0.3
    g = ch8_inv * 0.8 + ch13_inv * 0.2
    b = ch8_inv * 1.0

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_geoearthday(frame_dir: Path, sat: str, timestamp: str) -> Image.Image:
    """GeoColor-style daytime true color composite.

    Synthesizes a green channel from CH2 (red) and CH3 (veggie/NIR) since
    ABI has no native green band.  Uses the Bah et al. (2018) formula:
        simulated_green = 0.45*CH2 + 0.10*CH3 + 0.45*CH1
    Then applies simple Rayleigh scattering correction to sharpen land.
    """
    ch1 = load_band(frame_dir, sat, 1, timestamp)   # blue visible
    ch2 = load_band(frame_dir, sat, 2, timestamp)   # red visible
    ch3 = load_band(frame_dir, sat, 3, timestamp)   # veggie / NIR

    if ch1 is None or ch2 is None or ch3 is None:
        raise ValueError("Missing required bands (1, 2, 3)")

    ch1_n = normalize(ch1)
    ch2_n = normalize(ch2)
    ch3_n = normalize(ch3)

    # Synthesized green (Bah et al. 2018)
    green_syn = 0.45 * ch2_n + 0.10 * ch3_n + 0.45 * ch1_n

    # Simple Rayleigh correction: reduce blue haze, boost contrast
    rayleigh = 0.065
    r = np.clip(ch2_n - rayleigh, 0, 1)
    g = np.clip(green_syn - rayleigh * 0.8, 0, 1)
    b = np.clip(ch1_n - rayleigh * 1.2, 0, 1)

    # Gamma correction to brighten midtones (land surfaces)
    gamma = 1.0 / 1.3
    r = np.power(r, gamma)
    g = np.power(g, gamma)
    b = np.power(b, gamma)

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_custom(frame_dir: Path, sat: str, timestamp: str, r_band: int, g_band: int, b_band: int) -> Image.Image:
    """Custom RGB composite from user-selected bands."""
    r_data = load_band(frame_dir, sat, r_band, timestamp)
    g_data = load_band(frame_dir, sat, g_band, timestamp)
    b_data = load_band(frame_dir, sat, b_band, timestamp)

    if r_data is None:
        raise ValueError(f"Missing band {r_band}")
    if g_data is None:
        raise ValueError(f"Missing band {g_band}")
    if b_data is None:
        raise ValueError(f"Missing band {b_band}")

    r = np.clip(normalize(r_data) * 255, 0, 255).astype(np.uint8)
    g = np.clip(normalize(g_data) * 255, 0, 255).astype(np.uint8)
    b = np.clip(normalize(b_data) * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    sat = sys.argv[1]
    preset = sys.argv[2].lower()

    if sat not in ("GOES-18", "GOES-19"):
        print(f"Error: Invalid satellite {sat}")
        sys.exit(1)

    # Determine required bands
    if preset == "custom":
        if len(sys.argv) < 6:
            print("Error: Custom preset requires R_BAND G_BAND B_BAND")
            sys.exit(1)
        r_band = int(sys.argv[3])
        g_band = int(sys.argv[4])
        b_band = int(sys.argv[5])
        required_bands = list(set([r_band, g_band, b_band]))
    elif preset in PRESET_BANDS:
        required_bands = PRESET_BANDS[preset]
    else:
        print(f"Error: Unknown preset {preset}")
        sys.exit(1)

    frame_dir, timestamp = find_valid_frame(sat, required_bands)
    if frame_dir is None:
        print(f"Error: No valid frame found for {sat} with bands {required_bands}")
        sys.exit(1)

    print(f"Using frame: {frame_dir.name} (timestamp: {timestamp})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if preset == "daynight":
            img = make_daynight(frame_dir, sat, timestamp)
            out_name = f"{sat}_daynight.png"
        elif preset == "fire":
            img = make_fire(frame_dir, sat, timestamp)
            out_name = f"{sat}_fire.png"
        elif preset == "vegetation":
            img = make_vegetation(frame_dir, sat, timestamp)
            out_name = f"{sat}_vegetation.png"
        elif preset == "sandwich":
            img = make_sandwich(frame_dir, sat, timestamp)
            out_name = f"{sat}_sandwich.png"
        elif preset == "watervapor":
            img = make_watervapor(frame_dir, sat, timestamp)
            out_name = f"{sat}_watervapor.png"
        elif preset == "geoearthday":
            img = make_geoearthday(frame_dir, sat, timestamp)
            out_name = f"{sat}_geoearthday.png"
        elif preset == "custom":
            img = make_custom(frame_dir, sat, timestamp, r_band, g_band, b_band)
            out_name = f"{sat}_custom_R{r_band}_G{g_band}_B{b_band}.png"

        out_path = OUT_DIR / out_name
        img.save(out_path)

        # Write metadata
        meta = {
            "satellite": sat,
            "preset": preset,
            "source_frame": frame_dir.name,
            "timestamp": timestamp,
            "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output": out_name
        }
        if preset == "custom":
            meta["r_band"] = r_band
            meta["g_band"] = g_band
            meta["b_band"] = b_band

        meta_path = OUT_DIR / out_name.replace(".png", ".json")
        meta_path.write_text(json.dumps(meta, indent=2))

        # Ensure group write permission for www-data
        try:
            import os
            os.chmod(out_path, 0o664)
            os.chmod(meta_path, 0o664)
        except:
            pass

        print(f"Generated: {out_path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
