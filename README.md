
# GOES HRIT Live Web UI

## What This Is
This project converts live GOES HRIT reception via SatDump into a self-updating web dashboard.
As new Full Disk imagery arrives, the browser updates instantly via Server-Sent Events (SSE).

## Supported Satellites
- GOES-18
- GOES-19
- Multiple satellites simultaneously

## Architecture
RTL-SDR -> SatDump -> Filesystem -> Update Script -> SSE -> Browser

## Filesystem
/home/pi/sat/GOES-XX/IMAGES/GOES-XX/Full Disk/YYYY-MM-DD_HH-MM-SS/

## Installation
1. Install RaspiNOAA + SatDump
2. Clone repo
3. Run install/install.sh
4. Enable services
5. Open /goes

## USB Stability
echo 0 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb

## Security
Read-only nginx reverse proxy. Image-only exposure.

## Extras
- Mosaic builder
- Timelapse generator

## License
MIT
