#!/usr/bin/env python3
import json
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path("/var/www/goes")
TRIGGER = WEB_ROOT / ".trigger"
TIMELAPSE_SCRIPT = Path("/usr/local/bin/make_timelapse_gif.sh")
FALSECOLOR_SCRIPT = Path("/usr/local/bin/make_false_color.py")

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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/events":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found\n")
            return

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

            # Validate inputs
            if sat not in ("GOES-18", "GOES-19"):
                self.send_error_json(400, "Invalid satellite")
                return
            if band not in ("2", "7", "8", "13"):
                self.send_error_json(400, "Invalid band")
                return
            if hours not in ("3", "6", "12", "24"):
                self.send_error_json(400, "Invalid duration")
                return

            # Run the timelapse script (runs as current user, script handles permissions)
            result = subprocess.run(
                [str(TIMELAPSE_SCRIPT), sat, band, hours, frames],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {"success": True, "message": "GIF generated", "output": result.stdout.strip()}
                self.wfile.write(json.dumps(response).encode("utf-8"))
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

            # Validate inputs
            if sat not in ("GOES-18", "GOES-19"):
                self.send_error_json(400, "Invalid satellite")
                return

            valid_presets = ("daynight", "fire", "vegetation", "sandwich", "custom")
            if preset not in valid_presets:
                self.send_error_json(400, "Invalid preset")
                return

            # Build command
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

            # Run the false color script
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {"success": True, "message": "False color generated", "output": result.stdout.strip()}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            else:
                self.send_error_json(500, result.stderr.strip() or result.stdout.strip() or "Generation failed")

        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
        except subprocess.TimeoutExpired:
            self.send_error_json(504, "Generation timed out")
        except Exception as e:
            self.send_error_json(500, str(e))

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
