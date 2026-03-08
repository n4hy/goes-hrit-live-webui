#!/bin/bash
# Check if RTL-SDR is plugged in. If not, show a big red alarm on the desktop.
# Designed to run every 5 minutes via systemd timer.

VENDOR_PRODUCT="0bda:2838"
ALARM_PIDFILE="/tmp/rtlsdr_alarm.pid"

# Check if the device is present
if lsusb | grep -q "$VENDOR_PRODUCT"; then
    # Device is present — dismiss any existing alarm
    if [ -f "$ALARM_PIDFILE" ]; then
        kill "$(cat "$ALARM_PIDFILE")" 2>/dev/null
        rm -f "$ALARM_PIDFILE"
    fi
    exit 0
fi

# Device is missing — show alarm if not already showing
if [ -f "$ALARM_PIDFILE" ] && kill -0 "$(cat "$ALARM_PIDFILE")" 2>/dev/null; then
    exit 0  # alarm already on screen
fi

# Find active display
export DISPLAY=:0
export XAUTHORITY=/home/pi/.Xauthority

# Launch a big red alarm dialog
yad --title="RTL-SDR UNPLUGGED" \
    --text='<span font="48" foreground="red" weight="bold">RTL-SDR DISCONNECTED!\nPlug it back in!</span>' \
    --text-align=center \
    --width=800 --height=400 \
    --center \
    --no-buttons \
    --on-top \
    --undecorated \
    --skip-taskbar \
    --sticky &

echo $! > "$ALARM_PIDFILE"
