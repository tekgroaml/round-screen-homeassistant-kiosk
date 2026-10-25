"""Standard command line and background supervision for the Orbit scene."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from . import APP_ID, VERSION
from .config import ROOT, context, manifest, normalize, prepare
from .display import session_env
from .errors import AppError
from . import runtime


def parser():
    p = argparse.ArgumentParser(prog="./app", description="Orbit: one circular touchscreen on HDMI-A-1 or HDMI-A-2")
    p.add_argument("--version", action="version", version=VERSION)
    commands = p.add_subparsers(dest="action", required=True)
    info = commands.add_parser("info", help="Show version, implemented profiles and verification limits")
    info.add_argument("--json", action="store_true")
    for action in ("check", "run", "start"):
        s = commands.add_parser(action)
        for name in ("port", "shape", "panels", "input", "view", "data-source", "config", "content", "layout"):
            s.add_argument("--" + name, type=int if name in ("port", "panels") else str)
        s.add_argument("--context", help="Private normalized v1 context, mutually exclusive with public launch flags")
        if action == "start":
            s.add_argument("--replace", action="store_true")
        if action == "check":
            s.add_argument("--json", action="store_true")
    for action in ("status", "stop", "restart", "logs"):
        s = commands.add_parser(action)
        s.add_argument("--port", type=int, choices=(1, 2), required=action != "status")
        s.add_argument("--json", action="store_true")
        if action == "logs":
            s.add_argument("--follow", action="store_true")
    return p


def spec_from_args(args):
    fields = ("port", "shape", "panels", "input", "view", "data_source", "config", "content", "layout")
    values = {key: getattr(args, key) for key in fields if getattr(args, key) is not None}
    if args.context:
        if values or getattr(args, "replace", False):
            raise AppError("--context cannot be combined with public launch flags.", 2)
        return context(args.context)
    return normalize(values)


def environment():
    env = session_env()
    for key in list(env):
        if key.startswith("HA_") or key.startswith("KIOSK_"):
            env.pop(key)
    env["PYTHONPATH"] = str(ROOT)
    return env


def preflight(spec, env):
    _, digest, _ = prepare(spec)
    proc = subprocess.run([sys.executable, "-m", "orbit_app.display", str(spec["port"])],
                          cwd=ROOT, env=env, text=True, capture_output=True, timeout=20)
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise AppError("Display probe failed; install the Python GTK/Cairo runtime and log in to Wayland.", 5) from None
    if not result.get("ok"):
        raise AppError(result.get("error", "Display is not ready."), result.get("code", 5))
    return result["display"], digest


def stop(port):
    if not runtime.locked(port):
        return runtime.status(port)
    state = runtime.rpc(port)
    runtime.rpc(port, "stop", state["instance_id"])
    deadline = time.monotonic() + 12
    while runtime.locked(port):
        if time.monotonic() > deadline:
            raise AppError("Instance did not stop within 12 seconds; no unrelated PID was signalled.")
        time.sleep(.1)
    return runtime.status(port)


def spawn(spec, env):
    runtime.base(True)
    instance = uuid.uuid4().hex
    fd, filename = tempfile.mkstemp(prefix=".start-", suffix=".json", dir=runtime.base())
    with os.fdopen(fd, "w") as stream:
        json.dump({"spec": spec, "instance_id": instance}, stream)
    log = runtime.log_path(spec["port"])
    runtime.private_dir(log.parent)
    try:
        with log.open("a") as output:
            log.chmod(0o600)
            process = subprocess.Popen([sys.executable, "-m", "orbit_app.worker", filename],
                                       cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=output, start_new_session=True)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            state = runtime.read_state(spec["port"])
            ours = state.get("instance_id") == instance
            if ours and state.get("status") == "running":
                # Do not accept a stale ready file from an already exited child.
                if process.poll() is None:
                    return state
            code = process.poll()
            if code is not None:
                reported = state.get("error_code", code) if ours else code
                exit_code = reported if reported in (2, 3, 4, 5, 6, 7, 8) else 7
                raise AppError(state.get("error", "Scene worker exited before becoming ready.") if ours
                               else "Scene startup failed or another instance acquired the output.",
                               exit_code)
            if ours and state.get("status") == "failed":
                raise AppError(state.get("error", "Scene failed to start."), state.get("error_code", 7))
            time.sleep(.1)
        raise AppError("Scene startup timed out; inspect ./app logs --port " + str(spec["port"]))
    except BaseException:
        if "process" in locals() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # This is the exact child we created, never a PID read from a file.
                process.kill()
                process.wait(timeout=3)
        raise
    finally:
        Path(filename).unlink(missing_ok=True)


def start(spec, env, replace=False):
    _, digest = preflight(spec, env)
    old = None
    if runtime.locked(spec["port"]):
        active = runtime.rpc(spec["port"])
        if active.get("version") != VERSION:
            raise AppError("A different app version owns this instance. Stop it before starting the installed version.", 6)
        if active.get("features") == spec and active.get("config_digest") == digest and active.get("status") == "running":
            return active
        if not replace:
            raise AppError("Output is occupied or configuration changed; stop it or use --replace.", 4)
        # rpc enforces this app's ownership. Cross-project replacement is not implemented.
        old = active["features"]
        stop(spec["port"])
    try:
        return spawn(spec, env)
    except (AppError, OSError, subprocess.SubprocessError):
        if old:
            try:
                preflight(old, env)
                spawn(old, env)
            except (AppError, OSError, subprocess.SubprocessError):
                raise AppError("Replacement failed and the previous scene could not be restored. Inspect status/logs.") from None
            raise AppError("Replacement failed; the previous scene was restored.") from None
        raise


def logs(args):
    path = runtime.log_path(args.port)
    if not path.exists():
        print(json.dumps({"logs": []}) if args.json else "No logs for this output.")
        return
    with path.open() as stream:
        lines = deque(stream, maxlen=80)
        if args.json and not args.follow:
            print(json.dumps({"logs": [line.rstrip() for line in lines]}))
        else:
            for line in lines:
                print(json.dumps({"log": line.rstrip()}) if args.json else line.rstrip())
        if args.follow:
            while True:
                line = stream.readline()
                if line:
                    print(json.dumps({"log": line.rstrip()}) if args.json else line.rstrip(), flush=True)
                else:
                    time.sleep(.2)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == "info":
            print(json.dumps(manifest(), ensure_ascii=False, indent=2))
            return 0
        if args.action == "status":
            states = [runtime.status(port) for port in ((args.port,) if args.port else (1, 2))]
            print(json.dumps({"app_id": APP_ID, "version": VERSION, "instances": states}, ensure_ascii=False, indent=2))
            return 0
        if args.action == "logs":
            logs(args)
            return 0
        if args.action == "stop":
            print(json.dumps(stop(args.port), ensure_ascii=False))
            return 0
        if args.action == "restart":
            env = environment()
            state = runtime.status(args.port)
            spec = state.get("features")
            if not spec:
                raise AppError("No saved instance exists on this port.", 4)
            if state.get("version") != VERSION:
                raise AppError("Saved instance version differs. Stop it and start the installed version explicitly.", 6)
            spec = normalize(spec)
            preflight(spec, env)
            stop(args.port)
            print(json.dumps(spawn(spec, env), ensure_ascii=False))
            return 0
        spec = spec_from_args(args)
        prepare(spec)
        env = environment()
        if args.action == "check":
            screen, digest = preflight(spec, env)
            if runtime.locked(spec["port"]):
                raise AppError("The target output is occupied.", 4)
            print(json.dumps({"ok": True, "features": spec, "config_digest": digest, "display": screen}, ensure_ascii=False, indent=2))
        elif args.action == "start":
            print(json.dumps(start(spec, env, args.replace), ensure_ascii=False, indent=2))
        else:
            preflight(spec, env)
            for key in list(os.environ):
                if key.startswith("HA_") or key.startswith("KIOSK_"):
                    os.environ.pop(key)
            os.environ.update(env)
            from .worker import Worker
            return Worker(spec).run()
        return 0
    except AppError as exc:
        print(f"app: {exc}", file=sys.stderr)
        return exc.code
    except (OSError, subprocess.SubprocessError):
        print("app: Runtime I/O or subprocess failure. Check dependencies, session and instance logs.", file=sys.stderr)
        return 7
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
