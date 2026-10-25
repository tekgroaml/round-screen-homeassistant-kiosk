"""Contract, session geometry and lifecycle ownership regressions (no GTK required)."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from orbit_app import APP_ID, VERSION
from orbit_app.cli import main, spec_from_args, parser, start, spawn
from orbit_app.config import context, normalize, prepare
from orbit_app.display import geometry, matching_monitor, parse_outputs
from orbit_app.display import probe
from orbit_app.display import monitor
from orbit_app.display import test_conflict
from orbit_app.errors import AppError
from orbit_app import runtime
from orbit_app.worker import Worker


def spec(**changes):
    return normalize({"port": 1, "shape": "round", "panels": 1, "input": "touch", **changes})


class ContractTests(unittest.TestCase):
    def test_rejects_unimplemented_combinations_without_starting(self):
        for changes, code in (({"shape": "square"}, 3), ({"panels": 2}, 3), ({"input": "none"}, 3),
                              ({"content": "same"}, 3), ({"port": 0}, 2), ({"shape": "round,"}, 2),
                              ({"layout": "unknown"}, 3), ({"view": "weather"}, 3)):
            with self.subTest(changes=changes), self.assertRaises(AppError) as error:
                spec(**changes)
            self.assertEqual(error.exception.code, code)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["check", "--port", "1", "--shape", "square", "--input", "touch"]), 3)

    def test_context_cannot_bypass_capabilities_or_mix_public_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "context.json"
            data = spec()
            path.write_text(json.dumps(data)); path.chmod(0o600)
            self.assertEqual(context(path), data)
            data["shape"] = ["square"]
            path.write_text(json.dumps(data))
            with self.assertRaises(AppError): context(path)
            data["app_version"] = "unknown"
            path.write_text(json.dumps(data))
            with self.assertRaises(AppError) as error: context(path)
            self.assertEqual(error.exception.code, 6)
            args = parser().parse_args(["run", "--context", str(path), "--port", "1"])
            with self.assertRaises(AppError) as error: spec_from_args(args)
            self.assertEqual(error.exception.code, 2)

    def test_demo_ignores_inherited_live_credentials(self):
        with patch.dict(os.environ, {"HA_URL": "https://unexpected.invalid", "HA_TOKEN": "inherited-secret",
                                      "HA_CLIMATE_ENTITY": "invalid", "KIOSK_URL": "https://unexpected.invalid"}):
            _, _, backend = prepare(spec())
        self.assertEqual(backend.mode, "demo")
        self.assertEqual(backend.token, "")

    def test_live_requires_private_file_and_does_not_export_secret(self):
        with self.assertRaises(AppError) as error: prepare(spec(data_source="live"))
        self.assertEqual(error.exception.code, 8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            token = Path(tmp) / "token"
            token.write_text("fixture-only-secret"); token.chmod(0o644)
            path.write_text(json.dumps({"config_version": 1, "homeassistant": {
                "url": "https://homeassistant.invalid", "token_file": "token"}}))
            request = spec(config=str(path), data_source="live")
            with self.assertRaises(AppError): prepare(request)
            token.chmod(0o600)
            _, _, backend = prepare(request)
            self.assertEqual(backend.mode, "homeassistant")
            self.assertEqual(backend.token, "fixture-only-secret")
            self.assertNotIn("fixture-only-secret", json.dumps(request))

    def test_invalid_config_rejected_before_gui_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for settings in ({"config_version": 2}, {"config_version": 1, "room": ""},
                             {"config_version": 1, "safe_inset_percent": 99},
                             {"config_version": 1, "unexpected": True}):
                path.write_text(json.dumps(settings))
                with self.assertRaises(AppError): prepare(spec(config=str(path)))


class DisplayTests(unittest.TestCase):
    TEXT = '''HDMI-A-1 "Example"
  Enabled: yes
  Modes:
    800x800 px, 60.000000 Hz (preferred, current)
  Position: 720,0
  Transform: normal
  Scale: 1.000000
HDMI-A-2 "Example"
  Enabled: yes
  Modes:
    720x720 px, 60.000000 Hz (current)
  Position: 0,0
  Transform: normal
  Scale: 1.000000
'''

    def test_connector_mapping_uses_geometry_not_enumeration_or_position_order(self):
        output = parse_outputs(self.TEXT)["HDMI-A-1"]
        expected = geometry(output)
        self.assertEqual(expected, (720, 0, 800, 800))
        self.assertEqual(matching_monitor([(0, 0, 720, 720), expected], expected), 1)

    def test_ambiguous_or_incompatible_canvases_are_rejected(self):
        with self.assertRaises(AppError): matching_monitor([(0, 0, 480, 480)] * 2, (0, 0, 480, 480))
        output = parse_outputs(self.TEXT)["HDMI-A-1"]
        for change in ({"enabled": False}, {"scale": 2}, {"transform": "90"},
                       {"mode": {"width": 420, "height": 960}}, {"mode": {"width": 240, "height": 240}}):
            with self.subTest(change=change), self.assertRaises(AppError):
                geometry({**output, **change})

    def test_active_legacy_service_is_rejected_before_loading_gui(self):
        with patch("orbit_app.display.subprocess.run", return_value=Mock(returncode=0)), \
             patch("orbit_app.display.libraries") as gui:
            with self.assertRaises(AppError) as error: probe(1)
            self.assertEqual(error.exception.code, 4)
            gui.assert_not_called()

    def test_scaled_mirror_is_ambiguous_even_with_different_native_pixels(self):
        outputs = parse_outputs(self.TEXT)
        outputs["HDMI-A-2"].update(position=[720, 0], scale=2,
                                   mode={"width": 1600, "height": 1600, "refresh_hz": 60})
        with patch("orbit_app.display.outputs", return_value=outputs):
            with self.assertRaises(AppError) as error: monitor(1, Mock())
            self.assertEqual(error.exception.code, 3)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.tmp.name, "XDG_STATE_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_atomic_connector_lease_and_stale_pid_never_signalled(self):
        fd = runtime.lease(1)
        try:
            self.assertTrue(runtime.locked(1))
            with self.assertRaises(AppError) as error: runtime.lease(1)
            self.assertEqual(error.exception.code, 4)
            other = runtime.lease(2); os.close(other)
        finally: os.close(fd)
        runtime.atomic_json(runtime.paths(1)["state"], {"app_id": APP_ID, "port": 1, "pid": os.getpid(), "status": "running"})
        with patch("os.kill", side_effect=AssertionError("Must not signal PID files")):
            self.assertEqual(runtime.status(1)["status"], "stopped")

    def test_unlistened_test_socket_is_not_a_running_conflict(self):
        directory = Path(self.tmp.name) / "pi-setting-test"
        directory.mkdir()
        path = directory / "control.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
            stale.bind(str(path))
        test_conflict(1)
        self.assertTrue(path.exists(), "Do not delete another tool's stale socket")

    def test_control_socket_enforces_app_and_instance_ownership(self):
        runtime.base(True)
        worker = Worker(spec(), "fixture-instance")
        worker.GLib = Mock()
        worker.control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        worker.control.bind(str(runtime.paths(1)["socket"])); worker.control.listen(3); worker.control.settimeout(.1)
        thread = threading.Thread(target=worker.controls, daemon=True); thread.start()
        try:
            self.assertEqual(runtime.rpc(1)["instance_id"], "fixture-instance")
            with self.assertRaises(AppError): runtime.rpc(1, "stop", "wrong-instance")
            worker.GLib.idle_add.assert_not_called()
            runtime.rpc(1, "stop", "fixture-instance")
            worker.GLib.idle_add.assert_called_once()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(runtime.paths(1)["socket"]))
                client.sendall(b'{"action":"stop","app_id":"other-project"}\n')
                self.assertFalse(runtime.receive(client)["ok"])
        finally:
            worker.quitting = True; worker.control.close(); thread.join(timeout=1)


class LifecycleTests(unittest.TestCase):
    def test_native_worker_crash_uses_standard_startup_error_code(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"XDG_RUNTIME_DIR": tmp, "XDG_STATE_HOME": tmp}), \
             patch("orbit_app.cli.runtime.read_state", return_value={}), \
             patch("orbit_app.cli.subprocess.Popen") as popen:
            popen.return_value.poll.return_value = -11
            with self.assertRaises(AppError) as error: spawn(spec(), {})
            self.assertEqual(error.exception.code, 7)
            self.assertFalse(list(runtime.base().glob(".start-*.json")))

    def test_same_configuration_is_idempotent(self):
        request = spec()
        with patch("orbit_app.cli.preflight", return_value=({}, "digest")), \
             patch("orbit_app.cli.runtime.locked", return_value=True), \
             patch("orbit_app.cli.runtime.rpc", return_value={"version": VERSION, "features": request, "config_digest": "digest", "status": "running"}), \
             patch("orbit_app.cli.spawn") as spawn:
            self.assertEqual(start(request, {})["status"], "running")
            spawn.assert_not_called()

    def test_failed_replacement_restores_previous_scene(self):
        old = spec(port=1)
        new = spec(port=1, config="/example/new-config.json")
        with patch("orbit_app.cli.preflight", return_value=({}, "new-digest")), \
             patch("orbit_app.cli.runtime.locked", return_value=True), \
             patch("orbit_app.cli.runtime.rpc", return_value={"version": VERSION, "features": old, "config_digest": "old", "status": "running"}), \
             patch("orbit_app.cli.stop") as stop, \
             patch("orbit_app.cli.spawn", side_effect=[AppError("new failed"), {"status": "running"}]) as spawn:
            with self.assertRaises(AppError) as error: start(new, {}, replace=True)
            self.assertIn("was restored", str(error.exception))
            stop.assert_called_once_with(1)
            self.assertEqual(spawn.call_args_list[-1].args[0], old)

    def test_other_app_ownership_is_not_overridden_by_replace(self):
        with patch("orbit_app.cli.preflight", return_value=({}, "digest")), \
             patch("orbit_app.cli.runtime.locked", return_value=True), \
             patch("orbit_app.cli.runtime.rpc", side_effect=AppError("Another app owns this output", 4)), \
             patch("orbit_app.cli.stop") as stop:
            with self.assertRaises(AppError) as error: start(spec(), {}, replace=True)
            self.assertEqual(error.exception.code, 4)
            stop.assert_not_called()

    def test_replace_does_not_claim_to_roll_back_a_different_binary_version(self):
        with patch("orbit_app.cli.preflight", return_value=({}, "digest")), \
             patch("orbit_app.cli.runtime.locked", return_value=True), \
             patch("orbit_app.cli.runtime.rpc", return_value={"version": "0.1.0"}), \
             patch("orbit_app.cli.stop") as stop:
            with self.assertRaises(AppError) as error: start(spec(), {}, replace=True)
            self.assertEqual(error.exception.code, 6)
            stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
