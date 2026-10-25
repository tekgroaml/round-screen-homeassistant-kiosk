"""Read-only Wayland discovery and unambiguous connector-to-monitor matching."""
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

from .errors import AppError


def session_env():
    if sys.platform != "linux" or os.getuid() == 0:
        raise AppError("Run as the Raspberry Pi desktop user on Linux, without sudo.", 5)
    base = Path("/run/user") / str(os.getuid())
    sockets = sorted(p for p in base.glob("wayland-*") if p.is_socket())
    wanted = os.environ.get("WAYLAND_DISPLAY")
    selected = next((p for p in sockets if str(p) == wanted or p.name == wanted), None)
    if selected is None and wanted:
        raise AppError("WAYLAND_DISPLAY does not identify an active socket for this user.", 5)
    if selected is None:
        if len(sockets) != 1:
            raise AppError("No unique Wayland desktop. Log in to the desktop; with multiple sessions set WAYLAND_DISPLAY.", 5)
        selected = sockets[0]
    return dict(os.environ, XDG_RUNTIME_DIR=str(base), WAYLAND_DISPLAY=selected.name,
                DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(base / "bus"), GDK_BACKEND="wayland")


def parse_outputs(text):
    result, current = {}, None
    for line in text.splitlines():
        match = re.match(r'^(\S+)\s+"(.*)"$', line)
        if match:
            current = {"connector": match[1], "enabled": False, "position": [0, 0],
                       "scale": 1.0, "transform": "normal", "mode": None}
            result[match[1]] = current
        elif current is not None:
            field = line.strip()
            if field.startswith("Enabled:"):
                current["enabled"] = field.split(":", 1)[1].strip() == "yes"
            elif field.startswith("Position:"):
                current["position"] = [int(v) for v in field.split(":", 1)[1].split(",")]
            elif field.startswith("Scale:"):
                current["scale"] = float(field.split(":", 1)[1])
            elif field.startswith("Transform:"):
                current["transform"] = field.split(":", 1)[1].strip()
            else:
                mode = re.match(r"(\d+)x(\d+) px, ([\d.]+) Hz(.*)", field)
                if mode and "current" in mode[4]:
                    current["mode"] = {"width": int(mode[1]), "height": int(mode[2]), "refresh_hz": float(mode[3])}
    return result


def outputs():
    try:
        proc = subprocess.run(["wlr-randr"], text=True, capture_output=True, timeout=8)
        if proc.returncode:
            raise AppError("Cannot query Wayland outputs with wlr-randr.", 5)
        return parse_outputs(proc.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise AppError("Cannot read output geometry. Install wlr-randr and use a Wayland desktop.", 5) from None


def geometry(output):
    mode = output.get("mode")
    if not output.get("enabled") or not mode:
        raise AppError("The requested HDMI output is disconnected or disabled.", 3)
    if output["transform"] != "normal" or output["scale"] != 1:
        raise AppError("This preview requires output rotation 0 and desktop scale 100%. Configure the display first.", 3)
    width, height = mode["width"], mode["height"]
    if width != height or width < 360:
        raise AppError("Use a square logical canvas of at least 360x360 for the circular panel.", 3)
    return (*output["position"], width, height)


def matching_monitor(geometries, expected):
    matches = [i for i, value in enumerate(geometries) if tuple(value) == tuple(expected)]
    if len(matches) != 1:
        raise AppError("Cannot uniquely map HDMI to a desktop monitor; mirrored/stale layouts are unsupported.", 3)
    return matches[0]


def logical_rect(output):
    mode = output.get("mode")
    if not output.get("enabled") or not mode:
        return None
    width, height = mode["width"], mode["height"]
    if output["transform"] in ("90", "270", "flipped-90", "flipped-270"):
        width, height = height, width
    scale = output["scale"]
    if scale <= 0:
        raise AppError("Invalid desktop output scale.", 3)
    return (*output["position"], round(width / scale), round(height / scale))


def libraries():
    try:
        import gi
        import cairo
        for name, version in (("Gtk", "3.0"), ("Gdk", "3.0"), ("GtkLayerShell", "0.1")):
            gi.require_version(name, version)
        from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
        return Gdk, GLib, Gtk, GtkLayerShell
    except (ImportError, ValueError):
        raise AppError("Missing Python GTK/Cairo layer-shell runtime. Run ./setup.sh --install-only on the Pi.", 5) from None


def monitor(port, Gdk):
    all_outputs = outputs()
    name = f"HDMI-A-{port}"
    if name not in all_outputs:
        raise AppError(f"{name} is not connected.", 3)
    output = all_outputs[name]
    expected = geometry(output)
    # Reject duplicate logical output rectangles even if GDK collapses mirrors.
    if sum(1 for v in all_outputs.values() if logical_rect(v) == expected) != 1:
        raise AppError("Overlapping/mirrored outputs cannot be identified uniquely.", 3)
    display = Gdk.Display.get_default()
    if display is None:
        raise AppError("No active GDK Wayland display.", 5)
    monitors = [display.get_monitor(i) for i in range(display.get_n_monitors())]
    rects = [(r.x, r.y, r.width, r.height) for r in (m.get_geometry() for m in monitors)]
    selected = monitors[matching_monitor(rects, expected)]
    return output, selected, expected


def test_conflict(port):
    path = Path(os.environ["XDG_RUNTIME_DIR"]) / "pi-setting-test/control.sock"
    if not path.exists():
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            connection.connect(str(path))
            connection.sendall(b'{"action":"status"}\n')
            data = b""
            while b"\n" not in data and len(data) <= 65536:
                block = connection.recv(4096)
                if not block:
                    break
                data += block
        import json
        response = json.loads(data.split(b"\n")[0])
        if not response.get("ok"):
            raise ValueError()
    except (ConnectionRefusedError, FileNotFoundError):
        # A previous test may leave an inert socket file after its process exits.
        # Do not delete another tool's file; there is no listener to occupy us.
        return
    except (OSError, ValueError):
        raise AppError("A screen-test socket exists but cannot be queried. Check screen-test status first.", 4) from None
    if str(port) in response.get("screens", {}):
        raise AppError(f"screen-test occupies this output. Run screen-test stop --screen {port} first.", 4)


def probe(port):
    try:
        old = subprocess.run(["systemctl", "--user", "is-active", "--quiet", "round-display-kiosk.service"],
                             capture_output=True, timeout=3)
        if old.returncode == 0:
            raise AppError("Legacy kiosk service is active. Migrate it with ./scripts/install_service.sh --uninstall first.", 4)
    except (OSError, subprocess.TimeoutExpired):
        pass
    Gdk, _, Gtk, layer = libraries()
    ok = Gtk.init_check()
    if isinstance(ok, tuple):
        ok = ok[0]
    if not ok or not layer.is_supported():
        raise AppError("The desktop must support GTK layer-shell (labwc/Wayland).", 5)
    test_conflict(port)
    output, _, rect = monitor(port, Gdk)
    return {"connector": output["connector"], "native_mode": output["mode"],
            "viewport": {"width": rect[2], "height": rect[3]}, "output_binding": "gtk-layer-shell",
            "touch_validation": "pending-physical-test"}


def main():
    import json
    try:
        print(json.dumps({"ok": True, "display": probe(int(sys.argv[1]))}))
    except AppError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}))
        return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
