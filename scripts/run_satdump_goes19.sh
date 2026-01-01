#!/usr/bin/env bash
set -euo pipefail

# Wrapper for SatDump GOES-19 live decode using RTL-SDR.
# Intended to be invoked by systemd (satdump-goes19.service).

SATDUMP_BIN="${SATDUMP_BIN:-/home/pi/SatDump/build/satdump}"
FREQ="${FREQ:-1694.1e6}"
SR="${SR:-2.048e6}"
GAIN="${GAIN:-48}"
OUTROOT="${OUTROOT:-/home/pi/sat/goes19}"

exec "${SATDUMP_BIN}" live goes_hrit GOES-19 \
  --source rtlsdr \
  --frequency "${FREQ}" \
  --samplerate "${SR}" \
  --gain "${GAIN}" \
  --fill_missing \
  --output-directory "${OUTROOT}"
