"""Demo/live climate data using only the Python standard library (no UI server)."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import re
import threading
import time
from urllib.parse import urlsplit, quote
from urllib.request import Request


class Backend:
    def __init__(self, settings=None):
        settings = os.environ if settings is None else settings
        self.url = settings.get("HA_URL", "").rstrip("/")
        self.token = settings.get("HA_TOKEN", "")
        if bool(self.url) != bool(self.token):
            raise ValueError("Set both HA_URL and HA_TOKEN, or leave both unset for demo mode.")
        if self.url:
            parsed = urlsplit(self.url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("HA_URL must be an HTTP(S) base URL without credentials, query or fragment.")
        self.entities = {"temperature": settings.get("HA_TEMP_ENTITY", "sensor.living_room_temperature"),
                         "humidity": settings.get("HA_HUMIDITY_ENTITY", "sensor.living_room_humidity"),
                         "climate": settings.get("HA_CLIMATE_ENTITY", "climate.living_room"),
                         "weather": settings.get("HA_WEATHER_ENTITY", "weather.home")}
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
