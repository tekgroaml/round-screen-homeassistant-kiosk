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


class Backend:
    def __init__(self):
        self.url = os.environ.get("HA_URL", "").rstrip("/")
        self.token = os.environ.get("HA_TOKEN", "")
        if bool(self.url) != bool(self.token):
            raise ValueError("Set both HA_URL and HA_TOKEN, or leave both unset for demo mode.")
        if self.url:
            parsed = urlsplit(self.url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("HA_URL must be an HTTP(S) base URL without credentials, query or fragment.")
        self.entities = {"temperature": os.environ.get("HA_TEMP_ENTITY", "sensor.living_room_temperature"),
                         "humidity": os.environ.get("HA_HUMIDITY_ENTITY", "sensor.living_room_humidity"),
                         "climate": os.environ.get("HA_CLIMATE_ENTITY", "climate.living_room"),
                         "weather": os.environ.get("HA_WEATHER_ENTITY", "weather.home")}
        if any(not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", v) for v in self.entities.values()):
            raise ValueError("Entity IDs must use domain.object_id syntax.")
        if not self.entities["climate"].startswith("climate."):
            raise ValueError("HA_CLIMATE_ENTITY must be a climate entity.")
        self.lock = threading.Lock()
        self.target = 22.0

    @property
    def mode(self):
        return "homeassistant" if self.url else "demo"

    def ha(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(self.url + path, data=data, headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        # Reject redirects so the bearer token is never forwarded to a different host.
        from urllib.request import HTTPRedirectHandler, build_opener
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with build_opener(NoRedirect).open(request, timeout=2) as response:
            if response.status != 200:
                raise ValueError("Home Assistant returned an unexpected response.")
            return json.load(response)

    def require_celsius(self):
        configuration = self.ha("/api/config")
        if configuration.get("unit_system", {}).get("temperature") not in ("°C", "C"):
            raise ValueError("Home Assistant must be configured to use Celsius.")

    def state(self):
        if not self.url:
            with self.lock: target = self.target
            return {"temperature": round(21.4 + math.sin(time.time()/60)*.5, 1),
                    "humidity": round(44 + math.sin(time.time()/47)*4, 1),
                    "target": target, "weather": "sunny", "mode": self.mode}
        self.require_celsius()
        def read(key):
            return self.ha("/api/states/" + quote(self.entities[key], safe=""))
        keys = list(self.entities)
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = dict(zip(keys, pool.map(read, keys)))
        climate = values["climate"]["attributes"]
        # The UI is Celsius-only. Reject Fahrenheit entities rather than mislabeling them.
        unit = values["temperature"].get("attributes", {}).get("unit_of_measurement")
        climate_unit = climate.get("temperature_unit", "°C")
        if unit not in ("°C", "C") or climate_unit not in ("°C", "C"):
            raise ValueError("Configure Celsius temperature entities for this dashboard.")
        if values["humidity"].get("attributes", {}).get("unit_of_measurement") != "%":
            raise ValueError("The humidity sensor must use percent.")
        result = {"temperature": float(values["temperature"]["state"]), "humidity": float(values["humidity"]["state"]),
                  "target": float(climate["temperature"]), "weather": values["weather"]["state"], "mode": self.mode}
        if not all(math.isfinite(result[k]) for k in ("temperature", "humidity", "target")):
            raise ValueError("Home Assistant telemetry is unavailable.")
        if not 0 <= result["humidity"] <= 100 or not 16 <= result["target"] <= 30:
            raise ValueError("Telemetry exceeds the supported dashboard range.")
        return result

    def setpoint(self, value):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 16 <= value <= 30 or abs(value*2-round(value*2)) > 1e-6:
            raise ValueError("Target must be 16..30 Celsius in 0.5 degree steps.")
        # Serialize writes so a rapid dial gesture cannot reorder service calls.
        with self.lock:
            if self.url:
                self.require_celsius()
                climate = self.ha("/api/states/" + quote(self.entities["climate"], safe=""))["attributes"]
                if climate.get("temperature_unit", "°C") not in ("°C", "C"):
                    raise ValueError("The climate entity must use Celsius.")
                low, high = float(climate.get("min_temp", 16)), float(climate.get("max_temp", 30))
                step = float(climate.get("target_temp_step", .5))
                if not low <= value <= high or not math.isfinite(step) or step <= 0 or abs((value-low)/step-round((value-low)/step)) > 1e-5:
                    raise ValueError("Target is outside the climate entity's supported range or step.")
                self.ha("/api/services/climate/set_temperature", {"entity_id": self.entities["climate"], "temperature": value})
            self.target = value
        return {"target": value, "mode": self.mode}


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
        if path == "/api/state":
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
    a = p.parse_args()
    if not 1024 <= a.port <= 65535: p.error("Port must be 1024..65535.")
    try:
        backend = Backend()
        with ThreadingHTTPServer(("127.0.0.1", a.port), Handler) as server:
            server.backend = backend
            print(f"Dashboard server: http://127.0.0.1:{a.port} ({backend.mode})", flush=True)
            server.serve_forever()
    except KeyboardInterrupt: pass
    except (OSError, ValueError) as exc: p.exit(1, f"Server startup failed: {exc}\n")


if __name__ == "__main__": main()
