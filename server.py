#!/usr/bin/env python3
"""Loopback-only dashboard server and optional server-side Home Assistant adapter."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request

UI = Path(__file__).resolve().parent / "ui"


from orbit_app.backend import Backend


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        super().end_headers()

    def log_message(self, format, *args):
        # Avoid logging request paths, entity payloads or credentials.
        return

    def trusted(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin == "http://" + host)

    def reply(self, code, payload):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted():
            return self.reply(403, {"error": "Untrusted local origin."})
        path = urlsplit(self.path).path
        if path == "/api/ui-config":
            self.reply(200, getattr(self.server, "ui_config", {"room": "LIVING ROOM", "safe_inset_percent": 3}))
        elif path == "/api/state":
            try: self.reply(200, self.server.backend.state())
            except (OSError, ValueError, KeyError, TypeError, HTTPError, URLError):
                self.reply(502, {"error": "Telemetry unavailable. Check server-side Home Assistant settings."})
        elif path.startswith("/api/"):
            self.reply(404, {"error": "Unknown endpoint."})
        elif path in ("/", "/index.html", "/style.css", "/app.js"):
            super().do_GET()
        else:
            self.reply(404, {"error": "Not found."})

    def do_POST(self):
        self.close_connection = True
        if not self.trusted(): return self.reply(403, {"error": "Untrusted local origin."})
        if self.path != "/api/setpoint": return self.reply(404, {"error": "Unknown endpoint."})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.reply(415, {"error": "Use application/json."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid request length.")
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"target"}:
                raise ValueError("Supply one target field.")
            result = self.server.backend.setpoint(payload["target"])
        except (ValueError, TypeError) as exc:
            return self.reply(400, {"error": "Invalid target or unsupported climate range/step."})
        except (OSError, KeyError, HTTPError, URLError):
            return self.reply(502, {"error": "Home Assistant command failed."})
        self.reply(200, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--data-source", choices=("demo", "live"),
                   help="Explicitly select data source; omission preserves the legacy environment behavior")
    a = p.parse_args()
    if not 1024 <= a.port <= 65535: p.error("Port must be 1024..65535.")
    try:
        backend = Backend(settings={} if a.data_source == "demo" else None)
        if a.data_source == "live" and backend.mode != "homeassistant":
            raise ValueError("Live mode requires HA_URL and HA_TOKEN.")
        with ThreadingHTTPServer(("127.0.0.1", a.port), Handler) as server:
            server.backend = backend
            print(f"Dashboard server: http://127.0.0.1:{a.port} ({backend.mode})", flush=True)
            server.serve_forever()
    except KeyboardInterrupt: pass
    except (OSError, ValueError) as exc: p.exit(1, f"Server startup failed: {exc}\n")


if __name__ == "__main__": main()
