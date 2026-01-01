#!/usr/bin/env python3
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path("/var/www/goes")
TRIGGER = WEB_ROOT / ".trigger"

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
            self.send_response(404); self.end_headers()
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
    httpd.serve_forever()

if __name__ == "__main__":
    main()
