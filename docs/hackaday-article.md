# Real-Time GOES Weather Satellite Imagery From Your Backyard

*By Dr. Robert McGwier, N4HY*

There's something deeply satisfying about watching a hurricane develop in real-time on your own display—not through a weather website, but from radio signals you're pulling directly out of the sky. Every 10 minutes, a new full-disk image of Earth appears in my browser, pushed there by a Raspberry Pi sitting in my garage, fed by a dish antenna pointed at GOES-19 hovering 36,000 kilometers above the equator.

This isn't a weekend hack. It's infrastructure—a production-grade pipeline that runs unattended, publishing real-time satellite imagery to a web interface complete with historical browsing, animated timelapses, and six different false-color composites that reveal everything from active wildfires to upper-atmosphere water vapor. The entire system is open source, runs on a Raspberry Pi 5, and yes, you can build one too.

## The RF Challenge: Hearing a Whisper from Geosynchronous Orbit

GOES-18 and GOES-19 are NOAA's operational geostationary weather satellites, positioned at 137.2°W and 75.2°W respectively. They continuously broadcast High Rate Information Transmission (HRIT) data at 1694.1 MHz in the L-band—a frequency that presents real engineering challenges for amateur reception.

The link budget is unforgiving. Your signal has traveled 36,000 km through space, arriving at your antenna with a free-space path loss of approximately 187 dB. The satellite's EIRP (Effective Isotropic Radiated Power) is around 57 dBm, which means you're working with received signal levels in the neighborhood of -130 dBm at a modest dish. Every tenth of a dB matters.

### Hardware Requirements

The good news: you don't have to source components from five different vendors and hope they work together. Nooelec offers a complete, tested GOES reception kit that takes the guesswork out of hardware selection. Everything is available on Amazon:

**The Complete Signal Chain:**

```
Antenna Feed → FM Bandstop → SAWbird LNA → Coax → NESDR SMArTee XTR → USB → RPi5
```

**[Nooelec GOES Antenna System](https://a.co/d/5X87izo)** (~$90): A 60cm offset-feed dish with an integrated helix feed designed specifically for GOES L-band reception. The helix provides the LHCP (Left-Hand Circular Polarization) that GOES requires. Smaller than the 1-meter dishes often recommended, but paired with Nooelec's LNA, it works reliably.

[PHOTO: Nooelec GOES antenna system]

**[Nooelec SAWbird+ GOES LNA](https://a.co/d/dxBj0aZ)** (~$35): A filtered low-noise amplifier with a SAW bandpass filter centered on 1688 MHz. The integrated filtering rejects out-of-band interference while the LNA (0.5 dB noise figure) boosts the weak satellite signal. Bias-tee powered—draws power through the coax from the SDR.

[PHOTO: Nooelec SAWbird+ GOES]

**[Nooelec FM Bandstop Filter](https://a.co/d/2csqoZV)** (~$15): FM broadcast stations are everywhere, and their signals are strong enough to overload your SDR's front end, causing intermodulation products that can mask the GOES signal. This filter attenuates the 88-108 MHz FM band by 40+ dB. Install it between the antenna feed and the LNA.

[PHOTO: Nooelec FM Bandstop filter]

**[Nooelec NESDR SMArTee XTR SDR](https://a.co/d/9rSrJn6)** (~$35): An RTL-SDR with an extended tuning range, 0.5 PPM TCXO for frequency stability, and built-in bias-tee to power the LNA through the coax. The TCXO is important—cheap RTL-SDRs drift with temperature, making it hard to maintain lock on the GOES signal.

[PHOTO: Nooelec NESDR SMArTee XTR]

**Assembly**: Connect the components in order: antenna feed output → FM bandstop filter → SAWbird LNA input. Use the supplied coax from the LNA output to the SDR. Plug the SDR into a USB port on your Raspberry Pi 5. Total hardware cost: approximately $175 plus mounting hardware.

### Pointing the Antenna

Geostationary satellites stay fixed in the sky relative to your location, so you only need to point the dish once. But you need to point it accurately—the beam width of even a small dish is only a few degrees.

**Step 1: Find Your Pointing Angles**

Use the [N2YO satellite tracker](https://www.n2yo.com/) to calculate the azimuth and elevation for your location:

1. Go to n2yo.com and search for "GOES-19" (or GOES-18 if you're on the West Coast)
2. Click on the satellite, then select "Live Tracking"
3. Enter your location or allow GPS access
4. Note the **Azimuth** (compass direction) and **Elevation** (angle above horizon)

For example, from the East Coast, GOES-19 is roughly 180° azimuth (due south) and 45° elevation. From the West Coast, GOES-18 is around 210° azimuth and 40° elevation.

**Step 2: Rough Pointing**

Use a compass (or smartphone compass app) to aim the dish at the correct azimuth. Set the elevation using an inclinometer or smartphone level app. Get it close—within a few degrees.

**Step 3: Fine Tuning with Signal Lock**

Start SatDump and watch for signal lock:

```bash
satdump live goes_hrit . --source rtlsdr --samplerate 2.4e6 --frequency 1694.1e6 --gain 40
```

In the SatDump GUI, watch the signal metrics:
- **Viterbi Error Rate**: This is the key number. It should drop below 1000 when locked—the lower the better. Under 500 is solid, under 200 is excellent.
- **SNR (Signal-to-Noise Ratio)**: I regularly get 6-7 dB with the Nooelec setup. Anything above 4-5 dB works reliably.
- **Frame Lock**: The decoder status should show "LOCKED" or "SYNCED".

Slowly adjust azimuth and elevation while watching the SNR. Move in small increments—a quarter turn of the adjustment bolts—and wait a few seconds for the readings to stabilize. Peak the SNR, then tighten everything down.

Alternatively, use [goestools](https://github.com/pietern/goestools) `goesproc` with the `--monitor` flag to display real-time signal statistics, or run `rtl_power` to visualize the spectrum and confirm you're seeing the GOES carrier.

Once locked, you'll see imagery appearing in SatDump's output directory within minutes. Your dish is aimed—tighten the mount bolts and leave it.

### Making the Link Close

Here's the back-of-envelope link budget that proves this works with the Nooelec 60cm dish:

- Satellite EIRP: ~57 dBm
- Free-space path loss (36,000 km @ 1694 MHz): -187 dB
- Receive antenna gain (60cm dish): ~23 dBi
- SAWbird LNA gain: +22 dB
- System noise temperature: ~75 K (with SAWbird's 0.5 dB NF)
- Required Eb/N0 for BPSK: ~10 dB
- Margin: ~2-3 dB

It's tight, but it closes. The GOES HRIT signal uses rate-1/2 Viterbi-encoded BPSK at 927 kbps, and the concatenated Reed-Solomon coding provides additional error correction. With the Nooelec setup properly aimed, I regularly achieve 6-7 dB SNR—plenty of margin for reliable decoding. The real metric to watch is the Viterbi decoder error rate: keep it under 1000 and you're golden.

## Signal Processing: From RF to Pixels

### SatDump: The Heart of the System

The real magic happens in [SatDump](https://github.com/SatDump/SatDump), an extraordinary open-source satellite decoder created by Aang23 and a community of contributors. Without SatDump, this project wouldn't exist. It's the software equivalent of having a professional ground station—except it runs on a Raspberry Pi.

SatDump handles the entire GOES processing chain:

1. **SDR Interface**: Direct connection to RTL-SDR, Airspy, HackRF, and dozens of other SDR devices
2. **Demodulation**: Locks onto the 1694.1 MHz carrier and extracts the BPSK-modulated symbols
3. **Symbol Timing Recovery**: Synchronizes to the 927 kbaud symbol stream
4. **Viterbi Decoding**: Rate-1/2 convolutional code with constraint length 7
5. **Frame Synchronization**: Finds CCSDS frame boundaries in the bitstream
6. **Reed-Solomon Error Correction**: Fixes bit errors that survived Viterbi decoding
7. **Virtual Channel Demultiplexing**: Separates the multiplexed data streams (imagery, EMWIN text, DCS, etc.)
8. **JPEG2000 Decompression**: Reconstructs the final imagery from compressed packets
9. **PNG Output**: Writes calibrated, timestamped image files to disk

All of this runs in real-time on a Raspberry Pi 5. SatDump provides both a GUI for experimentation and a headless CLI mode perfect for unattended operation. It supports not just GOES, but Metop, NOAA APT, Meteor-M, Elektro-L, FengYun, and dozens of other satellites.

For GOES HRIT, I run SatDump in live mode:

```bash
satdump live goes_hrit . --source rtlsdr --samplerate 2.4e6 --frequency 1694.1e6 --gain 40
```

Let's break down these arguments:

- **`live`**: Run in real-time mode, continuously processing samples from the SDR. The alternative is `record` (save raw IQ to file) or processing a previously recorded file.

- **`goes_hrit`**: The decoder pipeline to use. SatDump includes dozens of pipelines for different satellites. This one handles the complete GOES HRIT processing chain—demodulation, Viterbi, Reed-Solomon, and image extraction.

- **`.`**: Output directory. SatDump creates subdirectories for each satellite and sector, with timestamped folders for each frame.

- **`--source rtlsdr`**: Which SDR driver to use. Options include `airspy`, `hackrf`, `rtltcp` (for remote SDRs), and many others. Use `rtlsdr` for the Nooelec NESDR SMArTee.

- **`--samplerate 2.4e6`**: Sample rate in Hz (2.4 MHz). GOES HRIT has a symbol rate of 927 kbaud, so you need at least ~1.8 MHz of bandwidth. 2.4 MHz provides comfortable margin and is a standard RTL-SDR sample rate.

- **`--frequency 1694.1e6`**: Center frequency in Hz (1694.1 MHz). This is the GOES HRIT downlink frequency. Both GOES-18 and GOES-19 use the same frequency—you receive whichever satellite your dish is pointed at.

- **`--gain 40`**: SDR gain setting. With the SAWbird LNA providing 22 dB of gain before the SDR, you don't need maximum SDR gain. A value of 40-49 typically works well. Too high causes clipping; too low buries the signal in noise. Adjust based on your Viterbi error rate.

A systemd service keeps SatDump running 24/7, automatically restarting if it crashes.

SatDump writes its output to a structured filesystem:

```
/home/pi/sat/GOES-19/IMAGES/GOES-19/
├── Full Disk/
│   ├── 2026-01-25_15-30-21/
│   │   ├── G19_2_20260125T153021Z.png   # CH2: Visible (0.64 μm)
│   │   ├── G19_7_20260125T153021Z.png   # CH7: Shortwave IR (3.9 μm)
│   │   ├── G19_8_20260125T153021Z.png   # CH8: Water Vapor (6.2 μm)
│   │   ├── G19_13_20260125T153021Z.png  # CH13: Longwave IR (10.3 μm)
│   │   └── product.cbor                  # Completion marker
│   └── ...
├── Mesoscale 1/
└── Mesoscale 2/
```

Each timestamped directory represents one complete frame. The `product.cbor` file is SatDump's completion marker—its presence guarantees all bands have been fully decoded and written. This becomes important in the software architecture.

### What You Actually Receive

GOES transmits multiple imaging sectors:

- **Full Disk**: The entire visible hemisphere, updated every 10-15 minutes. This is the iconic "blue marble" view showing North and South America, the Atlantic and Pacific oceans.

- **Mesoscale 1 & 2**: Two independently-targetable 1000×1000 km regions, updated every 60 seconds. NOAA points these at developing storms, wildfires, or other events requiring high temporal resolution.

The imagery spans multiple spectral bands. CH2 (visible) shows what your eyes would see. CH7 (shortwave IR at 3.9 μm) detects hot objects—fires appear as bright pixels even through smoke. CH8 (water vapor at 6.2 μm) reveals upper-tropospheric moisture patterns that indicate jet streams and atmospheric rivers. CH13 (longwave IR at 10.3 μm) provides the classic thermal view where cold cloud tops appear bright.

## Software Architecture: Infrastructure, Not a Demo

The core design philosophy is borrowed from production systems: determinism, idempotency, and stability. This isn't a script you babysit—it's infrastructure that runs unattended.

```
SDR (RTL-SDR, Airspy, etc.)
    ↓
SatDump (real-time HRIT decoder - the heart of the system)
    ↓
Filesystem (timestamped frames with PNG imagery)
    ↓
update_goes_multi_web.sh (publisher, every 60s via systemd)
    ↓
/var/www/goes/current/ (stable URLs)
    ↓
goes_sse_watch.py (SSE server + API)
    ↓
nginx (port 8080)
    ↓
Browser (real-time updates via SSE)
```

### The Publisher: Atomic Updates Only

The publisher script (`update_goes_multi_web.sh`) runs every 60 seconds via a systemd timer. It finds the newest complete frame by searching for directories containing a `product.cbor` file—ensuring partial frames are never published.

```bash
find "$ROOT" -type f -name 'product.cbor' -printf '%T@ %h\n' | sort -nr | head -n 1
```

It then copies the complete frame to `/var/www/goes/current/`, replacing the previous imagery atomically. URLs never change—`/goes/current/GOES-19/Full_Disk/G19_13_*.png` always points to the latest longwave IR image. Only the content changes.

After updating, it touches a trigger file:

```bash
touch /var/www/goes/.trigger
```

This is the key to efficient change detection.

### The SSE Server: Push, Don't Poll

The SSE (Server-Sent Events) daemon watches the trigger file's modification time with a simple 1-second poll loop:

```python
def watch():
    last = 0.0
    while True:
        m = TRIGGER.stat().st_mtime
        if m > last:
            last = m
            notify_update()
        time.sleep(1.0)
```

When an update is detected, it broadcasts to all connected browsers:

```python
def broadcast(msg: str):
    with lock:
        for w in list(clients):
            try:
                w.write(msg.encode("utf-8"))
            except Exception:
                dead.append(w)
        for w in dead:
            clients.discard(w)
```

Dead connections are automatically pruned. The browser receives an event and refreshes the display—no polling, no wasted bandwidth, no stale data.

### Zero-Cache Architecture

Every nginx location block includes aggressive cache-control headers:

```nginx
add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
```

For real-time data, staleness equals incorrectness. When a new hurricane image arrives, you want to see it immediately—not five minutes later when a cache expires.

## The Web Interface: Five Ways to See the Sky

The browser UI provides five operational modes:

### Live Mode

Real-time display with automatic refresh. Select your satellite (GOES-18 or GOES-19), sector (Full Disk, Mesoscale 1, Mesoscale 2), and band. When new imagery arrives, the SSE connection triggers a refresh—typically within seconds of the publisher completing its update.

### History Browser

Navigate through archived frames with First/Previous/Next/Last buttons or a dropdown selector. The API queries the filesystem for available timestamps and their associated bands. Useful for tracking a storm's development or finding that perfect cloud formation you saw earlier.

### Timelapse Generation

On-demand animated GIF creation. Select a band, time window (3, 6, 12, or 24 hours), and frame count. The server samples frames evenly across the time window using a smart selection algorithm:

```awk
awk -v total="$TOTAL" -v frames="$FRAMES" '
    BEGIN { step = total / frames }
    NR == 1 || NR >= int((count+1) * step) { print; count++ }
'
```

This distributes frames uniformly rather than clustering at one end—producing smooth, professional-looking timelapses.

### False Color Composites

Six presets that combine bands for specific applications:

- **Day/Night**: Blends visible (CH2) and inverted IR (CH13) weighted by solar illumination. Daytime shows true-color-ish imagery; nighttime shows thermal structure.

- **Fire/Hot Spot**: Boosts CH7 (shortwave IR) in the red channel. Active fires appear as bright red pixels even through smoke and haze.

- **Vegetation**: Pseudo-NDVI using CH2 and CH7 to highlight vegetation health.

- **Sandwich RGB**: Visible texture layered with IR cloud-top information for enhanced cloud structure.

- **Water Vapor**: CH8 (6.2 μm) reveals upper-level moisture. Jet streams, tropical moisture plumes, and atmospheric rivers become visible as flowing white patterns against a blue-black background.

- **Custom RGB**: Assign any available band to any color channel for experimental composites.

The processing uses NumPy for performance with per-band normalization to auto-adapt to varying scene brightness.

### EMWIN Weather Text

GOES also broadcasts EMWIN (Emergency Managers Weather Information Network)—text-based weather products including forecasts, watches, and warnings. The interface provides a scrollable list of recent products with full-text display.

[SCREENSHOTS: False color examples, timelapse GIF, history browser]

## Clever Engineering Details

A few implementation details that make the system robust:

**Path Security**: Every API endpoint that accepts file paths validates them with:

```python
image_path.resolve().relative_to(SAT_ROOT.resolve())
```

This prevents directory traversal attacks—a user can't craft a path that escapes the satellite data root.

**Graceful Degradation**: If a band is missing (perhaps SatDump dropped some packets), the false color presets fall back gracefully rather than crashing.

**Permission Handling**: The SSE server runs as the `pi` user (to access SatDump output in `/home/pi/sat`), while nginx runs as `www-data`. File permissions are set to 664 with group ownership of `www-data` for proper access control.

## Results: What You'll See

On a clear RF day, every frame decodes perfectly. You'll watch cold fronts sweep across the continent, tropical systems organize and intensify, and overnight thunderstorm complexes flare in the infrared. The fire detection preset has shown me wildfires that hadn't yet made the news.

The resolution isn't Google Earth—Full Disk images are roughly 5 km per pixel—but you're seeing the actual photons that hit the satellite's sensor minutes ago. There's no third-party processing, no API rate limits, no subscription. Just physics and software.

## Build Your Own

Everything is open source at [github.com/n4hy/goes-hrit-live-webui](https://github.com/n4hy/goes-hrit-live-webui).

### Hardware Shopping List

All available on Amazon (total ~$175 + Pi):

- [Nooelec GOES Antenna System](https://a.co/d/5X87izo) - 60cm dish with helix feed
- [Nooelec SAWbird+ GOES LNA](https://a.co/d/dxBj0aZ) - filtered low-noise amplifier
- [Nooelec FM Bandstop Filter](https://a.co/d/2csqoZV) - prevents FM broadcast interference
- [Nooelec NESDR SMArTee XTR](https://a.co/d/9rSrJn6) - RTL-SDR with TCXO and bias-tee
- Raspberry Pi 5 with power supply and SD card
- Mounting hardware for your installation (tripod, pole mount, etc.)

### Software Installation

**Step 1: Install SatDump**

SatDump is available as pre-built packages for Raspberry Pi OS:

```bash
# Add the SatDump repository
curl -s https://apt.satdump.org/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/satdump-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/satdump-archive-keyring.gpg] https://apt.satdump.org/apt stable main" | sudo tee /etc/apt/sources.list.d/satdump.list

# Install
sudo apt update
sudo apt install satdump
```

Alternatively, build from source at [github.com/SatDump/SatDump](https://github.com/SatDump/SatDump).

**Step 2: Configure SatDump for GOES**

Create a systemd service to run SatDump continuously:

```bash
# /etc/systemd/system/satdump-goes.service
[Unit]
Description=SatDump GOES HRIT Decoder
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/sat
ExecStart=/usr/bin/satdump live goes_hrit . --source rtlsdr --samplerate 2.4e6 --frequency 1694.1e6 --gain 40
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start: `sudo systemctl enable --now satdump-goes`

**Step 3: Install the Web UI**

```bash
git clone https://github.com/n4hy/goes-hrit-live-webui ~/goes-hrit-live-webui
cd ~/goes-hrit-live-webui
sudo bash install/install.sh
```

The installer sets up nginx, systemd services, and all dependencies. Point your browser at `http://[pi-ip]:8080/` and wait for your first frame.

First light is magical. The globe appears, band by band, as SatDump finishes decoding. Within 15 minutes you'll have a complete Full Disk image—your image, from your antenna, from 36,000 km away.

## What's Next

Future development targets:

- **Geographic overlays**: State and country boundaries, lat/lon grids
- **Multi-satellite composites**: Merge GOES-18 West and GOES-19 East coverage
- **Storm detection**: ML-based identification of developing convection
- **APRS integration**: Push weather alerts to ham radio networks

The bones are solid. The architecture scales. And the view never gets old.

---

*Dr. Robert McGwier (N4HY) is a signal processing researcher and amateur radio operator. This project runs 24/7 from his home. The complete source code is available at [github.com/n4hy/goes-hrit-live-webui](https://github.com/n4hy/goes-hrit-live-webui).*
