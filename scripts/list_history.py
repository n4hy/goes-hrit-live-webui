#!/usr/bin/env python3
"""
List available historical frames for a satellite/sector.
Returns JSON array of timestamp directories sorted newest first.
"""

import json
import sys
from pathlib import Path

SAT_ROOT = "/home/pi/sat/{sat}/IMAGES/{sat}/{sector}"

def list_frames(sat: str, sector: str, limit: int = 100) -> list:
    """List available frames for satellite/sector."""
    root = Path(SAT_ROOT.format(sat=sat, sector=sector))
    if not root.exists():
        return []

    frames = []
    for d in root.iterdir():
        if d.is_dir() and (d / "product.cbor").exists():
            # Get list of available bands
            bands = []
            for png in d.glob("G??_*_*.png"):
                # Extract band number from filename like G19_13_20260125T153021Z.png
                parts = png.stem.split("_")
                if len(parts) >= 2:
                    try:
                        band = int(parts[1])
                        if band not in bands:
                            bands.append(band)
                    except ValueError:
                        pass

            frames.append({
                "dir": d.name,
                "bands": sorted(bands),
                "mtime": d.stat().st_mtime
            })

    # Sort by directory name (which contains timestamp) descending
    frames.sort(key=lambda x: x["dir"], reverse=True)

    return frames[:limit]

def main():
    if len(sys.argv) < 3:
        print("Usage: list_history.py <SAT> <SECTOR> [LIMIT]")
        sys.exit(1)

    sat = sys.argv[1]
    sector = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    frames = list_frames(sat, sector, limit)
    print(json.dumps(frames))

if __name__ == "__main__":
    main()
