#!/usr/bin/env python3
"""
Generate false color composite images from GOES ABI bands.
Usage: make_false_color.py <SAT> <PRESET> [R_BAND] [G_BAND] [B_BAND]

Presets:
  daynight  - CH2 (visible) blended with CH13 (IR) based on sun angle
  fire      - CH7 (shortwave IR) highlights hot spots
  vegetation - CH2 + CH3 combination
  sandwich  - CH2 (visible) + CH13 (IR) sandwich blend
  custom    - Requires R_BAND, G_BAND, B_BAND arguments
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

def find_latest_frame(sat: str) -> Path | None:
    """Find the most recent Full Disk frame directory."""
    root = Path(SAT_ROOT.format(sat=sat))
    if not root.exists():
        return None

    dirs = sorted(root.iterdir(), reverse=True)
    for d in dirs:
        if d.is_dir() and (d / "product.cbor").exists():
            return d
    return None

def load_band(frame_dir: Path, sat: str, band: int) -> np.ndarray | None:
    """Load a band image as grayscale numpy array."""
    sat_num = sat.replace("GOES-", "")
    pattern = f"G{sat_num}_{band}_*.png"
    files = list(frame_dir.glob(pattern))
    if not files:
        return None

    img = Image.open(files[0]).convert('L')
    return np.array(img, dtype=np.float32) / 255.0

def normalize(arr: np.ndarray) -> np.ndarray:
    """Normalize array to 0-1 range."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-6:
        return arr
    return (arr - mn) / (mx - mn)

def make_daynight(frame_dir: Path, sat: str) -> Image.Image:
    """Day/Night composite: visible by day, IR by night."""
    ch2 = load_band(frame_dir, sat, 2)   # Visible
    ch13 = load_band(frame_dir, sat, 13) # Longwave IR

    if ch2 is None or ch13 is None:
        raise ValueError("Missing required bands (2, 13)")

    # Simple blend: use visible brightness to weight
    # Brighter visible = more daytime = use visible
    # Darker visible = nighttime = use IR (inverted for clouds=white)
    vis_weight = normalize(ch2)
    ir_inv = 1.0 - normalize(ch13)  # Invert so cold clouds are bright

    # Blend
    r = vis_weight * ch2 + (1 - vis_weight) * ir_inv
    g = vis_weight * ch2 * 0.9 + (1 - vis_weight) * ir_inv * 0.9
    b = vis_weight * ch2 * 0.8 + (1 - vis_weight) * ir_inv

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_fire(frame_dir: Path, sat: str) -> Image.Image:
    """Fire/Hot Spot: CH7 shortwave IR highlights fires."""
    ch2 = load_band(frame_dir, sat, 2)   # Visible
    ch7 = load_band(frame_dir, sat, 7)   # Shortwave IR (fire)
    ch13 = load_band(frame_dir, sat, 13) # Longwave IR

    if ch7 is None:
        raise ValueError("Missing required band 7")

    ch7_n = normalize(ch7)

    # Fire pixels are hot in CH7
    # Red channel = CH7 boosted
    # Green = visible or IR
    # Blue = IR inverted
    r = np.clip(ch7_n * 1.5, 0, 1)  # Boost fire signal

    if ch2 is not None:
        g = normalize(ch2) * 0.7
    else:
        g = ch7_n * 0.5

    if ch13 is not None:
        b = (1.0 - normalize(ch13)) * 0.6
    else:
        b = ch7_n * 0.3

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_vegetation(frame_dir: Path, sat: str) -> Image.Image:
    """Vegetation composite using visible bands."""
    ch2 = load_band(frame_dir, sat, 2)   # Red visible
    ch7 = load_band(frame_dir, sat, 7)   # Near-IR proxy
    ch13 = load_band(frame_dir, sat, 13) # Thermal

    if ch2 is None:
        raise ValueError("Missing required band 2")

    ch2_n = normalize(ch2)

    # Pseudo vegetation index
    if ch7 is not None:
        ch7_n = normalize(ch7)
        # NDVI-like: vegetation appears green
        r = ch2_n * 0.8
        g = ch7_n * 0.9 + ch2_n * 0.3
        b = ch2_n * 0.5
    else:
        r = ch2_n
        g = ch2_n * 1.2
        b = ch2_n * 0.7

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_sandwich(frame_dir: Path, sat: str) -> Image.Image:
    """Sandwich RGB: visible + IR blend."""
    ch2 = load_band(frame_dir, sat, 2)   # Visible
    ch13 = load_band(frame_dir, sat, 13) # Longwave IR

    if ch2 is None or ch13 is None:
        raise ValueError("Missing required bands (2, 13)")

    ch2_n = normalize(ch2)
    ch13_inv = 1.0 - normalize(ch13)  # Invert: cold=bright

    # Sandwich blend: visible for texture, IR for cloud tops
    r = ch2_n * 0.6 + ch13_inv * 0.4
    g = ch2_n * 0.5 + ch13_inv * 0.5
    b = ch13_inv * 0.8 + ch2_n * 0.2

    r = np.clip(r * 255, 0, 255).astype(np.uint8)
    g = np.clip(g * 255, 0, 255).astype(np.uint8)
    b = np.clip(b * 255, 0, 255).astype(np.uint8)

    return Image.fromarray(np.stack([r, g, b], axis=-1), mode='RGB')

def make_custom(frame_dir: Path, sat: str, r_band: int, g_band: int, b_band: int) -> Image.Image:
    """Custom RGB composite from user-selected bands."""
    r_data = load_band(frame_dir, sat, r_band)
    g_data = load_band(frame_dir, sat, g_band)
    b_data = load_band(frame_dir, sat, b_band)

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

    frame_dir = find_latest_frame(sat)
    if frame_dir is None:
        print(f"Error: No frames found for {sat}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if preset == "daynight":
            img = make_daynight(frame_dir, sat)
            out_name = f"{sat}_daynight.png"
        elif preset == "fire":
            img = make_fire(frame_dir, sat)
            out_name = f"{sat}_fire.png"
        elif preset == "vegetation":
            img = make_vegetation(frame_dir, sat)
            out_name = f"{sat}_vegetation.png"
        elif preset == "sandwich":
            img = make_sandwich(frame_dir, sat)
            out_name = f"{sat}_sandwich.png"
        elif preset == "custom":
            if len(sys.argv) < 6:
                print("Error: Custom preset requires R_BAND G_BAND B_BAND")
                sys.exit(1)
            r_band = int(sys.argv[3])
            g_band = int(sys.argv[4])
            b_band = int(sys.argv[5])
            img = make_custom(frame_dir, sat, r_band, g_band, b_band)
            out_name = f"{sat}_custom_R{r_band}_G{g_band}_B{b_band}.png"
        else:
            print(f"Error: Unknown preset {preset}")
            sys.exit(1)

        out_path = OUT_DIR / out_name
        img.save(out_path)

        # Write metadata
        meta = {
            "satellite": sat,
            "preset": preset,
            "source_frame": frame_dir.name,
            "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output": out_name
        }
        if preset == "custom":
            meta["r_band"] = r_band
            meta["g_band"] = g_band
            meta["b_band"] = b_band

        meta_path = OUT_DIR / out_name.replace(".png", ".json")
        meta_path.write_text(json.dumps(meta, indent=2))

        try:
            import pwd
            import os
            www_data = pwd.getpwnam("www-data")
            os.chown(out_path, www_data.pw_uid, www_data.pw_gid)
            os.chown(meta_path, www_data.pw_uid, www_data.pw_gid)
        except:
            pass

        print(f"Generated: {out_path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
