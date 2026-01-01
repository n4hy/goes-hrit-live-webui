#!/usr/bin/env python3
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sat")
    ap.add_argument("--pair", nargs=2)
    ap.add_argument("--band", default="13")
    args = ap.parse_args()

    print("Mosaic builder is a provided stub.")
    print("Recommended implementations:")
    print("  - ImageMagick: montage + convert")
    print("  - Python Pillow: image grid compose")
    print("Publish mosaics into /var/www/goes/mosaics/")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
