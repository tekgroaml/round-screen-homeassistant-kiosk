"""Strict public features and private backend configuration (no network I/O)."""
import hashlib
import json
import os
from pathlib import Path
import stat

from . import APP_ID, VERSION
from .errors import AppError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = {"config_version": 1, "room": "LIVING ROOM", "safe_inset_percent": 3}


def read_json(path, limit=65536):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > limit:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, TypeError):
        raise AppError("Cannot read a valid, bounded JSON object from the configuration file.", 6) from None


def manifest():
    return json.loads((ROOT / "screen-app.json").read_text())


def expand(value, count, allowed):
    parts = value.split(",") if isinstance(value, str) else value
    if not isinstance(parts, list) or len(parts) not in (1, count) or any(v not in allowed for v in parts):
        raise AppError("Invalid shape/input list; supply one value or one per panel.", 2)
    return parts * count if len(parts) == 1 else parts


def normalize(values):
    """Reused by direct CLI, restart and internal context; no capability bypass."""
    port = values.get("port")
    panels = values.get("panels", 1)
    if type(port) is not int or port not in (1, 2) or type(panels) is not int or panels not in (1, 2):
        raise AppError("Use --port 1 or 2 and --panels 1 or 2.", 2)
    shape = expand(values.get("shape"), panels, ("square", "round", "rect", "strip"))
    inputs = expand(values.get("input", "none"), panels, ("touch", "none"))
    view = values.get("view") or "climate"
    source = values.get("data_source", "demo")
    if panels != 1 or shape != ["round"] or inputs != ["touch"] or view != "climate":
        raise AppError("This project supports only round + one panel + touch + climate.", 3)
    if values.get("layout") is not None or values.get("content") is not None:
        raise AppError("Single-panel Orbit does not accept --layout or --content.", 3)
    if source not in ("demo", "live"):
        raise AppError("Use --data-source demo or live.", 2)
    path = values.get("config")
    if path is not None and not isinstance(path, str):
        raise AppError("Configuration path must be text.", 6)
    return {"contract_version": 1, "app_id": APP_ID, "app_version": VERSION,
            "port": port, "shape": shape, "panels": 1, "input": inputs,
            "profile_id": "round-touch", "topology": "single-panel", "view": view,
            "data_source": source, "config": str(Path(path).expanduser().resolve()) if path else None}


def context(path):
    path = Path(path)
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AppError("Context must be a private file owned by the desktop user.", 6)
    except OSError:
        raise AppError("Cannot read the runtime context.", 6) from None
    data, _ = read_json(path)
    if data.get("contract_version") != 1 or data.get("app_id") != APP_ID or data.get("app_version") != VERSION:
        raise AppError("Incompatible runtime context/app version.", 6)
    if data.get("owner") not in (None, os.getuid()):
        raise AppError("Runtime context belongs to another user.", 6)
    return normalize(data)


def load_config(spec):
    result = dict(DEFAULT_CONFIG)
    digest = "default"
    if spec["config"]:
        user, digest = read_json(spec["config"])
        if set(user) - {"config_version", "room", "safe_inset_percent", "homeassistant"} or user.get("config_version") != 1:
            raise AppError("Unsupported configuration schema; use config_version 1.", 6)
        result.update(user)
    room = result["room"]
    inset = result["safe_inset_percent"]
    if not isinstance(room, str) or not 1 <= len(room) <= 28 or any(ord(c) < 32 for c in room):
        raise AppError("Room must be 1..28 printable characters.", 6)
    if type(inset) not in (int, float) or not 0 <= inset <= 10:
        raise AppError("safe_inset_percent must be 0..10.", 6)
    return result, digest


def backend_settings(spec, config):
    # Explicitly empty for demo: inherited HA_* and KIOSK_URL cannot activate live.
    if spec["data_source"] == "demo":
        return {}
    ha = config.get("homeassistant")
    if not isinstance(ha, dict) or set(ha) - {"url", "token_file", "entities"} or not ha.get("url") or not ha.get("token_file"):
        raise AppError("Live mode requires homeassistant.url and token_file in --config.", 8)
    if not isinstance(ha["url"], str) or not isinstance(ha["token_file"], str):
        raise AppError("Invalid Home Assistant settings.", 6)
    token_path = Path(ha["token_file"]).expanduser()
    if not token_path.is_absolute():
        token_path = Path(spec["config"]).parent / token_path
    try:
        info = token_path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
            raise ValueError()
        token = token_path.read_text().strip()
        if not token or any(c.isspace() for c in token):
            raise ValueError()
    except (OSError, ValueError):
        raise AppError("Live token_file must be a nonempty private file owned by this user (chmod 600).", 8) from None
    entities = ha.get("entities", {})
    names = {"temperature": "HA_TEMP_ENTITY", "humidity": "HA_HUMIDITY_ENTITY",
             "climate": "HA_CLIMATE_ENTITY", "weather": "HA_WEATHER_ENTITY"}
    if not isinstance(entities, dict) or set(entities) - set(names) or any(not isinstance(v, str) for v in entities.values()):
        raise AppError("Invalid Home Assistant entity settings.", 6)
    return {"HA_URL": ha["url"], "HA_TOKEN": token, **{names[k]: v for k, v in entities.items()}}


def prepare(spec):
    from .backend import Backend
    config, digest = load_config(spec)
    settings = backend_settings(spec, config)
    try:
        backend = Backend(settings=settings)
    except (ValueError, TypeError):
        raise AppError("Invalid server-side Home Assistant URL or entity settings.", 6) from None
    return config, digest, backend
