# Security Notes (Public-Safe Reverse Proxy)

This repo is designed to be exposed **safely**, but only if you follow these guidelines.

## Principle: only expose what you intend

Expose only a single URL path:
- `/goes/`

Do **not** expose:
- your entire RaspiNOAA admin surface
- directory listings you did not intend
- other services on the Pi

## Recommended public exposure patterns

### Option 1: VPN-only (best)
Use Tailscale or WireGuard. No port forwarding required. You browse as if you were at home.

### Option 2: Cloudflare Tunnel
Public URL without exposing inbound ports. Good for home networks. Adds Cloudflare access controls.

### Option 3: Direct port-forward (least preferred)
If you forward 443 from your router, do this **minimum set**:
- HTTPS only (no plain HTTP)
- Basic auth or SSO in front
- Rate limiting
- Only allow `/goes/` routes
- Disable any unintended autoindex
- Keep OS patched

## Basic auth

```bash
sudo apt-get update
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-goes youruser
```

## Logs to watch

- `/var/log/nginx/access.log`
- `/var/log/nginx/error.log`
- `journalctl -u goes-sse.service`
- `journalctl -u update-goes-fd-web.service`
