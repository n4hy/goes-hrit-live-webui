#!/usr/bin/env bash
set -euo pipefail

# Publish latest GOES-19 Full Disk images into a web directory.
# Writes:
#   ${WEB_ROOT}/latest_*.png
#   ${WEB_ROOT}/meta.json
#
# Selection policy:
# - Determine newest timestamp directory under ${SATDUMP_FD_ROOT} that contains ANCHOR.
# - Copy mapped products per /etc/goes_fd_views.conf
#
# Environment overrides:
# - SATDUMP_FD_ROOT, WEB_ROOT, VIEWMAP, ANCHOR

SATDUMP_FD_ROOT="${SATDUMP_FD_ROOT:-/home/pi/sat/goes19/IMAGES/GOES-19/Full Disk}"
WEB_ROOT="${WEB_ROOT:-/var/www/goes}"
VIEWMAP="${VIEWMAP:-/etc/goes_fd_views.conf}"
ANCHOR="${ANCHOR:-product.cbor}"

umask 0022
install -d -m 0755 "${WEB_ROOT}"

LATEST_DIR=""

while IFS= read -r d; do
  if [[ -f "${SATDUMP_FD_ROOT}/${d}/${ANCHOR}" ]]; then
    LATEST_DIR="${d}"
    break
  fi
done < <(find "${SATDUMP_FD_ROOT}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)

if [[ -z "${LATEST_DIR}" ]]; then
  echo "No Full Disk directory containing anchor '${ANCHOR}' found under: ${SATDUMP_FD_ROOT}" >&2
  exit 1
fi

# Copy products
if [[ ! -f "${VIEWMAP}" ]]; then
  echo "Missing view map: ${VIEWMAP}" >&2
  exit 1
fi

while IFS= read -r line; do
  [[ -z "${line}" ]] && continue
  [[ "${line}" =~ ^# ]] && continue
  out="${line%%=*}"
  src="${line#*=}"
  src_path="${SATDUMP_FD_ROOT}/${LATEST_DIR}/${src}"
  out_path="${WEB_ROOT}/${out}"
  if [[ -f "${src_path}" ]]; then
    install -m 0644 "${src_path}" "${out_path}"
    chown www-data:www-data "${out_path}" 2>/dev/null || true
  fi
done < "${VIEWMAP}"

# Meta
ts_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "${WEB_ROOT}/meta.json" <<EOF
{
  "timestamp_dir": "${LATEST_DIR}",
  "updated_utc": "${ts_utc}"
}
EOF
chown www-data:www-data "${WEB_ROOT}/meta.json" 2>/dev/null || true
chmod 0644 "${WEB_ROOT}/meta.json"
