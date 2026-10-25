"""Native Python/GTK/Cairo scene: one surface, one data adapter, no web engine."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import signal
import socket
import sys
import threading
import time
import uuid

from . import APP_ID, VERSION, display, runtime
from .config import normalize, prepare
from .drawing import draw
from .errors import AppError
from .touch import Dial, local_point


class Worker:
    def __init__(self, spec, instance_id=None):
        self.spec = normalize(spec)
        self.instance_id = instance_id or uuid.uuid4().hex
        self.port = self.spec["port"]
        self.exit_code = 0
        self.ready = self.quitting = self.has_data = self.drawn = False
        self.control = self.window = self.lease = self.executor = None
        self.model = Dial()
        self.revision = 0
        self.pending_write = False
        self.write_timer = None
        self.polling = False
        self.last_native = -10.0
        self.state = {"app_id": APP_ID, "version": VERSION, "contract_version": 1,
                      "instance_id": self.instance_id, "owner": os.getuid(),
                      "port": self.port, "connector": f"HDMI-A-{self.port}",
                      "renderer": "python-gtk-cairo", "status": "starting", "health": "starting",
                      "features": self.spec, "touch_validation": "pending-physical-test",
                      "touch_events": 0, "pointer_events": 0, "target": 22.0}

    def persist(self):
        self.state["target"] = self.model.target
        runtime.atomic_json(runtime.paths(self.port)["state"], self.state)

    def event(self, name, **details):
        print(json.dumps({"contract_version": 1, "instance_id": self.instance_id,
                          "event": name, "details": details}, ensure_ascii=False), flush=True)

    def fail(self, message, code=7):
        if self.quitting:
            return False
        self.exit_code = code
        self.state.update(status="failed", health="failed", error=message, error_code=code)
        self.persist()
        self.event("error", message=message, code=code)
        self.quit()
        return False

    def quit(self, *_):
        if self.quitting:
            return False
        self.quitting = True
        if self.window:
            self.window.destroy()
        self.Gtk.main_quit()
        return False

    def controls(self):
        while not self.quitting:
            try:
                client, _ = self.control.accept()
            except (OSError, socket.timeout):
                continue
            with client:
                client.settimeout(2)
                try:
                    message = runtime.receive(client)
                    if message.get("app_id") != APP_ID or message.get("instance_id", self.instance_id) != self.instance_id:
                        reply = {"ok": False, "code": 4, "error": "Instance ownership mismatch."}
                    elif message.get("action") not in ("status", "stop"):
                        reply = {"ok": False, "code": 2, "error": "Unknown instance action."}
                    else:
                        reply = {"ok": True, "state": dict(self.state)}
                        if message["action"] == "stop":
                            self.GLib.idle_add(self.quit)
                    client.sendall(json.dumps(reply).encode() + b"\n")
                except (OSError, ValueError):
                    pass

    def verify_surface(self):
        rect = self.target.get_geometry()
        selected = self.Gdk.Display.get_default().get_monitor_at_window(self.window.get_window())
        allocation = self.window.get_allocation()
        if (selected != self.target or (rect.x, rect.y, rect.width, rect.height) != self.expected
                or (allocation.width, allocation.height) != self.expected[2:]):
            self.fail("Cannot verify the scene on the requested HDMI output.", 3)
            return False
        return True

    def mark_ready(self):
        if self.quitting or self.ready or not self.drawn or not self.has_data:
            return False
        if self.verify_surface():
            self.ready = True
            self.state.update(status="running", health="ok", started_at=time.time())
            self.persist()
            self.event("ready", connector=self.state["connector"], viewport=self.state["viewport"], renderer="python-gtk-cairo")
        return False

    def paint(self, area, context):
        if self.quitting:
            return False
        try:
            draw(context, area.get_allocated_width(), area.get_allocated_height(), self.model, self.config)
            self.drawn = True
            if not self.ready:
                self.GLib.idle_add(self.mark_ready)
        except Exception as exc:
            self.GLib.idle_add(self.fail, f"Native drawing failed ({type(exc).__name__}).", 7)
        return False

    def submit(self, function, callback, *args):
        def done(future):
            try:
                value = future.result()
                error = False
            except Exception:
                value, error = None, True
            if not self.quitting:
                self.GLib.idle_add(callback, value, error)
        self.executor.submit(function, *args).add_done_callback(done)

    def poll(self):
        if self.quitting:
            return False
        if self.polling or self.pending_write:
            return True
        self.polling = True
        revision = self.revision
        def received(value, error):
            self.polling = False
            if self.quitting:
                return False
            if error:
                self.model.feedback, self.model.error = "OFFLINE · LAST DATA", True
                self.state["health"] = "degraded-telemetry"
            else:
                self.model.sample(value, update_target=revision == self.revision and not self.pending_write)
                self.has_data = True
                self.state["health"] = "ok"
                self.mark_ready()
            self.area.queue_draw()
            self.persist()
            return False
        self.submit(self.backend.state, received)
        return True

    def queue_write(self, value):
        self.revision += 1
        revision = self.revision
        self.pending_write = True
        if self.write_timer:
            self.GLib.source_remove(self.write_timer)
        def send():
            self.write_timer = None
            def saved(result, error):
                if self.quitting:
                    return False
                if revision == self.revision:
                    self.pending_write = False
                    if error:
                        if self.model.active is None:
                            self.model.target = self.model.authoritative
                        self.model.feedback, self.model.error = "TARGET NOT SAVED", True
                        self.state["health"] = "degraded-write"
                    else:
                        self.model.authoritative = result["target"]
                        if self.model.active is None:
                            self.model.target = result["target"]
                            self.model.feedback = "TARGET SENT TO HA" if result["mode"] == "homeassistant" else "DEMO TARGET SAVED"
                            self.model.error = False
                        self.state["health"] = "ok"
                    self.area.queue_draw()
                    self.persist()
                return False
            self.submit(self.backend.setpoint, saved, value)
            return False
        self.write_timer = self.GLib.timeout_add(200, send)

    def interact(self, kind, sequence, source, x, y):
        if not self.ready or self.quitting:
            return
        if kind == "begin":
            self.state["touch_events" if source == "native_touch" else "pointer_events"] += 1
            if source == "native_touch":
                self.state["touch_validation"] = "native-touch-observed; verify-position-physically"
        x, y = local_point(x, y, self.area.get_allocated_width(), self.area.get_allocated_height(),
                           self.config["safe_inset_percent"])
        commit = self.model.event(kind, sequence, source, x, y)
        if commit is not None:
            self.queue_write(commit)
        self.area.queue_draw()
        if kind in ("begin", "end", "cancel"):
            self.persist()

    def on_touch(self, area, event):
        kinds = {self.Gdk.EventType.TOUCH_BEGIN: "begin", self.Gdk.EventType.TOUCH_UPDATE: "update",
                 self.Gdk.EventType.TOUCH_END: "end", self.Gdk.EventType.TOUCH_CANCEL: "cancel"}
        kind = kinds.get(event.type)
        if kind:
            self.last_native = time.monotonic()
            self.interact(kind, event.get_event_sequence(), "native_touch", event.x, event.y)
        # Consume native touch so GTK does not also turn it into a second click.
        return True

    def on_pointer(self, area, event):
        if time.monotonic() - self.last_native < .5:
            return True
        if event.type == self.Gdk.EventType.BUTTON_PRESS and event.button == 1:
            kind = "begin"
        elif event.type == self.Gdk.EventType.BUTTON_RELEASE and event.button == 1:
            kind = "end"
        elif event.type == self.Gdk.EventType.MOTION_NOTIFY and event.state & self.Gdk.ModifierType.BUTTON1_MASK:
            kind = "update"
        else:
            return True
        self.interact(kind, "pointer", "pointer_or_emulated", event.x, event.y)
        return True

    def tick(self):
        if self.quitting:
            return False
        if not self.ready and time.monotonic() - self.begin > 28:
            return self.fail("Native scene/telemetry did not become ready. Check live settings and runtime logs.")
        try:
            display.test_conflict(self.port)
            output, _, expected = display.monitor(self.port, self.Gdk)
            if expected != self.expected or output["mode"] != self.state["native_mode"]:
                return self.fail("Display topology changed; configure it and restart this scene.", 3)
            if self.ready and not self.verify_surface():
                return False
        except AppError as exc:
            return self.fail(str(exc), exc.code)
        if self.ready:
            self.event("health", health=self.state["health"], target=self.model.target)
        return True

    def clock_tick(self):
        if self.quitting:
            return False
        self.area.queue_draw()
        return True

    def run(self):
        self.lease = runtime.lease(self.port)
        try:
            self.config, digest, self.backend = prepare(self.spec)
            self.state["config_digest"] = digest
            self.Gdk, self.GLib, self.Gtk, layer = display.libraries()
            ok = self.Gtk.init_check()
            if not (ok[0] if isinstance(ok, tuple) else ok) or not layer.is_supported():
                raise AppError("No supported Wayland layer-shell desktop.", 5)
            display.test_conflict(self.port)
            output, self.target, self.expected = display.monitor(self.port, self.Gdk)
            self.state.update(native_mode=output["mode"], viewport={"width": self.expected[2], "height": self.expected[3]},
                              output_binding="gtk-layer-shell", profile_id="round-touch")
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orbit-data")
            self.control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            path = runtime.paths(self.port)["socket"]
            path.unlink(missing_ok=True)
            self.control.bind(str(path)); path.chmod(0o600)
            self.control.listen(8); self.control.settimeout(.5)
            threading.Thread(target=self.controls, daemon=True).start()
            self.persist()

            self.window = self.Gtk.Window(title="Orbit · " + self.state["connector"])
            self.window.set_decorated(False)
            layer.init_for_window(self.window)
            layer.set_namespace(self.window, APP_ID + f"-port{self.port}")
            layer.set_layer(self.window, layer.Layer.OVERLAY)
            layer.set_monitor(self.window, self.target)
            layer.set_exclusive_zone(self.window, -1)
            layer.set_keyboard_mode(self.window, getattr(layer.KeyboardMode, "ON_DEMAND", layer.KeyboardMode.NONE))
            for edge in (layer.Edge.TOP, layer.Edge.BOTTOM, layer.Edge.LEFT, layer.Edge.RIGHT):
                layer.set_anchor(self.window, edge, True)
                layer.set_margin(self.window, edge, 0)
            self.area = self.Gtk.DrawingArea()
            self.area.add_events(self.Gdk.EventMask.TOUCH_MASK | self.Gdk.EventMask.BUTTON_PRESS_MASK |
                                 self.Gdk.EventMask.BUTTON_RELEASE_MASK | self.Gdk.EventMask.POINTER_MOTION_MASK)
            for event, callback in (("draw", self.paint), ("touch-event", self.on_touch),
                                    ("button-press-event", self.on_pointer), ("button-release-event", self.on_pointer),
                                    ("motion-notify-event", self.on_pointer)):
                self.area.connect(event, callback)
            self.window.add(self.area)
            self.window.connect("delete-event", lambda *_: (self.quit(), True)[1])
            self.window.connect("key-press-event", self.key)
            self.window.connect("realize", self.hide_cursor)
            self.begin = time.monotonic()
            self.GLib.unix_signal_add(self.GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit)
            self.GLib.unix_signal_add(self.GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)
            self.window.show_all()
            self.poll()
            self.GLib.timeout_add_seconds(1, self.clock_tick)
            self.GLib.timeout_add_seconds(10, self.poll)
            self.GLib.timeout_add_seconds(10, self.tick)
            self.Gtk.main()
        except AppError as exc:
            self.state.update(status="failed", health="failed", error=str(exc), error_code=exc.code)
            self.exit_code = exc.code
            self.event("error", message=str(exc), code=exc.code)
        except Exception as exc:
            self.state.update(status="failed", health="failed", error=f"Native scene failed ({type(exc).__name__}).", error_code=7)
            self.exit_code = 7
            self.event("error", message=self.state["error"], code=7)
        finally:
            self.quitting = True
            if self.window:
                self.window.destroy()
            if self.executor:
                self.executor.shutdown(wait=True, cancel_futures=True)
            if self.control:
                self.control.close()
                runtime.paths(self.port)["socket"].unlink(missing_ok=True)
            if self.state["status"] != "failed":
                self.state.update(status="stopped", health="stopped")
            self.persist()
            self.event("stopped", status=self.state["status"])
            os.close(self.lease)
        return self.exit_code

    def hide_cursor(self, *_):
        self.window.get_window().set_cursor(self.Gdk.Cursor.new_for_display(self.Gdk.Display.get_default(), self.Gdk.CursorType.BLANK_CURSOR))

    def key(self, _, event):
        if event.keyval == self.Gdk.KEY_Escape:
            self.quit()
            return True
        return False


def main():
    from .config import read_json
    request, _ = read_json(sys.argv[1])
    try:
        return Worker(request["spec"], request["instance_id"]).run()
    except AppError as exc:
        print(json.dumps({"event": "error", "details": {"message": str(exc), "code": exc.code}}), flush=True)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
