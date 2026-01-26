#!/usr/bin/env python3
import json
import subprocess
import time
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path("/var/www/goes")
TRIGGER = WEB_ROOT / ".trigger"
TIMELAPSE_SCRIPT = Path("/usr/local/bin/make_timelapse_gif.sh")
FALSECOLOR_SCRIPT = Path("/usr/local/bin/make_false_color.py")
HISTORY_SCRIPT = Path("/usr/local/bin/list_history.py")
SAT_ROOT = Path("/home/pi/sat")
EMWIN_PATHS = [
    "/home/pi/sat/GOES-19/EMWIN",
    "/home/pi/sat/GOES-19/PRODUCTS/EMWIN",
    "/home/pi/sat/goes19/EMWIN",
]

HOST = "127.0.0.1"
PORT = 8090

clients = set()
lock = threading.Lock()

def broadcast(msg: str):
    dead = []
    with lock:
        for w in list(clients):
            try:
                w.write(msg.encode("utf-8"))
                w.flush()
            except Exception:
                dead.append(w)
        for w in dead:
            clients.discard(w)

def notify_update():
    broadcast(f"event: update\ndata: {time.time()}\n\n")

def find_emwin_dir():
    """Find where EMWIN products are stored."""
    for p in EMWIN_PATHS:
        path = Path(p)
        if path.exists() and path.is_dir():
            return path
    # Try to find it
    for sat_dir in SAT_ROOT.glob("*/"):
        for emwin in sat_dir.rglob("*EMWIN*"):
            if emwin.is_dir():
                return emwin
    return None

def list_emwin_products(limit=50):
    """List recent EMWIN text products."""
    emwin_dir = find_emwin_dir()
    if not emwin_dir:
        return []

    products = []
    for f in emwin_dir.rglob("*.txt"):
        try:
            products.append({
                "path": str(f.relative_to(emwin_dir)),
                "name": f.name,
                "mtime": f.stat().st_mtime,
                "size": f.stat().st_size
            })
        except:
            pass

    # Also check for .TXT files
    for f in emwin_dir.rglob("*.TXT"):
        try:
            products.append({
                "path": str(f.relative_to(emwin_dir)),
                "name": f.name,
                "mtime": f.stat().st_mtime,
                "size": f.stat().st_size
            })
        except:
            pass

    products.sort(key=lambda x: x["mtime"], reverse=True)
    return products[:limit]

def read_emwin_product(path):
    """Read content of an EMWIN text product."""
    emwin_dir = find_emwin_dir()
    if not emwin_dir:
        return None

    full_path = emwin_dir / path
    # Security: ensure path doesn't escape emwin_dir
    try:
        full_path.resolve().relative_to(emwin_dir.resolve())
    except ValueError:
        return None

    if full_path.exists() and full_path.is_file():
        try:
            return full_path.read_text(errors='replace')
        except:
            return None
    return None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/events":
            self.handle_sse()
        elif path == "/api/history":
            self.handle_history(query)
        elif path == "/api/history/image":
            self.handle_history_image(query)
        elif path == "/api/emwin":
            self.handle_emwin_list(query)
        elif path == "/api/emwin/read":
            self.handle_emwin_read(query)
        elif path == "/api/sectors":
            self.handle_sectors()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found\n")

    def handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        self.wfile.write(b"event: hello\ndata: connected\n\n")
        self.wfile.flush()

        with lock:
            clients.add(self.wfile)

        try:
            while True:
                time.sleep(3600)
        except Exception:
            pass
        finally:
            with lock:
                clients.discard(self.wfile)

    def handle_history(self, query):
        sat = query.get("sat", ["GOES-19"])[0]
        sector = query.get("sector", ["Full Disk"])[0]
        limit = int(query.get("limit", ["100"])[0])

        try:
            result = subprocess.run(
                ["python3", str(HISTORY_SCRIPT), sat, sector, str(limit)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.send_json_response(200, json.loads(result.stdout))
            else:
                self.send_error_json(500, result.stderr or "Failed to list history")
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_history_image(self, query):
        """Serve a historical image from satdump directory."""
        sat = query.get("sat", [None])[0]
        sector = query.get("sector", [None])[0]
        dir_name = query.get("dir", [None])[0]
        file_name = query.get("file", [None])[0]

        if not all([sat, sector, dir_name, file_name]):
            self.send_error_json(400, "Missing parameters (sat, sector, dir, file)")
            return

        # Validate satellite
        if sat not in ("GOES-18", "GOES-19"):
            self.send_error_json(400, "Invalid satellite")
            return

        # Validate sector - convert underscores back to spaces
        sector = sector.replace("_", " ")
        if sector not in ("Full Disk", "Mesoscale 1", "Mesoscale 2"):
            self.send_error_json(400, "Invalid sector")
            return

        # Validate file extension
        if not file_name.endswith(".png"):
            self.send_error_json(400, "Invalid file type")
            return

        # Build path
        image_path = SAT_ROOT / sat / "IMAGES" / sat / sector / dir_name / file_name

        # Security: ensure path doesn't escape sat root
        try:
            image_path.resolve().relative_to(SAT_ROOT.resolve())
        except ValueError:
            self.send_error_json(403, "Invalid path")
            return

        if image_path.exists() and image_path.is_file():
            try:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(image_path.read_bytes())
            except Exception as e:
                self.send_error_json(500, str(e))
        else:
            self.send_error_json(404, "Image not found")

    def handle_emwin_list(self, query):
        limit = int(query.get("limit", ["50"])[0])
        products = list_emwin_products(limit)
        self.send_json_response(200, {"products": products, "found": len(products) > 0})

    def handle_emwin_read(self, query):
        path = query.get("path", [None])[0]
        if not path:
            self.send_error_json(400, "Missing path parameter")
            return

        content = read_emwin_product(path)
        if content is not None:
            self.send_json_response(200, {"content": content, "path": path})
        else:
            self.send_error_json(404, "Product not found")

    def handle_sectors(self):
        """List available satellite/sector combinations."""
        sectors = []
        current_dir = WEB_ROOT / "current"
        if current_dir.exists():
            for sat_dir in current_dir.iterdir():
                if sat_dir.is_dir():
                    for sector_dir in sat_dir.iterdir():
                        if sector_dir.is_dir():
                            sectors.append({
                                "satellite": sat_dir.name,
                                "sector": sector_dir.name.replace("_", " ")
                            })
        self.send_json_response(200, sectors)

    def do_POST(self):
        if self.path == "/api/timelapse":
            self.handle_timelapse()
        elif self.path == "/api/falsecolor":
            self.handle_falsecolor()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found\n")

    def handle_timelapse(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)

            sat = data.get("sat", "GOES-19")
            band = data.get("band", "13")
            hours = data.get("hours", "6")
            frames = data.get("frames", "24")
            reject_bad = data.get("reject_bad", True)

            if sat not in ("GOES-18", "GOES-19"):
                self.send_error_json(400, "Invalid satellite")
                return
            if band not in ("2", "7", "8", "13"):
                self.send_error_json(400, "Invalid band")
                return
            if hours not in ("3", "6", "12", "24"):
                self.send_error_json(400, "Invalid duration")
                return

            cmd = [str(TIMELAPSE_SCRIPT), sat, band, hours, frames]
            if reject_bad:
                cmd.append("--reject-bad")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                self.send_json_response(200, {"success": True, "message": "GIF generated", "output": result.stdout.strip()})
            else:
                self.send_error_json(500, result.stderr.strip() or result.stdout.strip() or "Generation failed")

        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
        except subprocess.TimeoutExpired:
            self.send_error_json(504, "Generation timed out")
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_falsecolor(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)

            sat = data.get("sat", "GOES-19")
            preset = data.get("preset", "daynight")

            if sat not in ("GOES-18", "GOES-19"):
                self.send_error_json(400, "Invalid satellite")
                return

            valid_presets = ("daynight", "fire", "vegetation", "sandwich", "watervapor", "custom")
            if preset not in valid_presets:
                self.send_error_json(400, "Invalid preset")
                return

            cmd = ["python3", str(FALSECOLOR_SCRIPT), sat, preset]

            if preset == "custom":
                r_band = data.get("r_band", "2")
                g_band = data.get("g_band", "7")
                b_band = data.get("b_band", "13")

                valid_bands = ("2", "7", "8", "13", "14")
                if r_band not in valid_bands or g_band not in valid_bands or b_band not in valid_bands:
                    self.send_error_json(400, "Invalid band selection")
                    return

                cmd.extend([r_band, g_band, b_band])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                self.send_json_response(200, {"success": True, "message": "False color generated", "output": result.stdout.strip()})
            else:
                self.send_error_json(500, result.stderr.strip() or result.stdout.strip() or "Generation failed")

        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
        except subprocess.TimeoutExpired:
            self.send_error_json(504, "Generation timed out")
        except Exception as e:
            self.send_error_json(500, str(e))

    def send_json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "error": message}).encode("utf-8"))

    def log_message(self, fmt, *args):
        return

def watch():
    last = 0.0
    while True:
        try:
            m = TRIGGER.stat().st_mtime
            if m > last:
                last = m
                notify_update()
        except FileNotFoundError:
            pass
        time.sleep(1.0)

def main():
    threading.Thread(target=watch, daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SSE server listening on {HOST}:{PORT}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
