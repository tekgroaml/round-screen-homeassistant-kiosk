"""Per-user connector leases and private, bounded local control messages."""
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import tempfile

from . import APP_ID
from .errors import AppError


def private_dir(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise AppError("Unsafe runtime directory ownership/type.", 5)
    path.chmod(0o700)
    return path


def base(create=False):
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "screen-app"
    return private_dir(root) if create else root


def paths(port):
    root = base()
    return {"lock": root / f"port{port}.lock", "socket": root / f"port{port}.sock",
            "state": root / f"port{port}.json"}


def log_path(port):
    root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return root / "screen-app" / APP_ID / f"port{port}.log"


def atomic_json(path, data):
    path = Path(path)
    private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".orbit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def lease(port):
    base(True)
    path = paths(port)["lock"]
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        os.close(fd)
        raise AppError("Unsafe connector lock.", 5)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise AppError(f"HDMI-A-{port} is already owned by another scene instance.", 4) from None
    return fd


def locked(port):
    path = paths(port)["lock"]
    if not path.exists():
        return False
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True
        finally:
            os.close(fd)
    except OSError:
        raise AppError("Cannot safely inspect connector ownership.", 4) from None


def read_state(port):
    try:
        value = json.loads(paths(port)["state"].read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def rpc(port, action="status", instance=None):
    message = {"action": action, "app_id": APP_ID}
    if instance:
        message["instance_id"] = instance
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(paths(port)["socket"]))
            connection.sendall(json.dumps(message).encode() + b"\n")
            response = receive(connection)
    except (OSError, ValueError):
        raise AppError("The running instance control socket is unavailable; no unrelated PID will be signalled.", 4) from None
    if not response.get("ok"):
        raise AppError(response.get("error", "Instance ownership mismatch."), response.get("code", 4))
    return response["state"]


def receive(connection):
    data = b""
    while b"\n" not in data:
        chunk = connection.recv(4096)
        if not chunk:
            raise ValueError("Closed control connection")
        data += chunk
        if len(data) > 65536:
            raise ValueError("Oversized control message")
    result = json.loads(data.split(b"\n", 1)[0])
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def status(port):
    if locked(port):
        record = read_state(port)
        if record.get("app_id") not in (None, APP_ID):
            return {"app_id": APP_ID, "port": port, "status": "occupied", "occupant": record["app_id"]}
        return rpc(port)
    previous = read_state(port)
    if previous.get("app_id") != APP_ID:
        return {"app_id": APP_ID, "port": port, "status": "stopped"}
    result = dict(previous)
    if result.get("status") not in ("stopped", "failed"):
        result.update(status="stopped", health="worker-not-running")
    return result
