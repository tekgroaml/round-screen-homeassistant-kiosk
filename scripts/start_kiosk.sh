#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ $(id -u) != 0 ]] || { echo "Launch Chromium as the desktop user, not root." >&2; exit 1; }
[[ -n ${WAYLAND_DISPLAY:-}${DISPLAY:-} ]] || { echo "A logged-in graphical desktop is required." >&2; exit 1; }
if command -v chromium >/dev/null; then browser=chromium
elif command -v chromium-browser >/dev/null; then browser=chromium-browser
else echo "Install Chromium using ./setup.sh --install-only." >&2; exit 1; fi
port=${KIOSK_PORT:-8765}
[[ $port =~ ^[0-9]{4,5}$ ]] && (( 10#$port >= 1024 && 10#$port <= 65535 )) || { echo "Invalid KIOSK_PORT." >&2; exit 1; }
url=${KIOSK_URL:-http://127.0.0.1:$port/}
[[ $url == http://* || $url == https://* ]] || { echo "KIOSK_URL must be HTTP(S)." >&2; exit 1; }
profile=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/round-kiosk.XXXXXXXX")
server_pid=; browser_pid=; cursor_pid=
cleanup() {
  trap - EXIT INT TERM
  for pid in "$browser_pid" "$server_pid" "$cursor_pid"; do
    if [[ -n $pid ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  done
  rm -rf -- "$profile"
}
trap cleanup EXIT
trap 'exit 0' INT TERM
local_url="http://127.0.0.1:$port/"
if [[ $url == "$local_url" || $url == "http://localhost:$port/" ]]; then
  python3 server.py --port "$port" & server_pid=$!
  python3 - "$port" "$server_pid" <<'CHECK'
import os, sys, time, urllib.request
port, pid = map(int, sys.argv[1:])
for attempt in range(40):
    try:
        os.kill(pid, 0)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=.5) as response:
            if response.status == 200: break
    except (OSError, ValueError):
        time.sleep(.1)
else:
    raise SystemExit("Local dashboard server did not become ready.")
CHECK
  kill -0 "$server_pid" 2>/dev/null || { echo "Local server exited; the port may already be occupied." >&2; exit 1; }
fi
if [[ -n ${WAYLAND_DISPLAY:-} ]]; then ozone=wayland
else
  ozone=x11
  if command -v unclutter >/dev/null; then unclutter -idle 0.1 -root & cursor_pid=$!; fi
fi
"$browser" --kiosk --no-first-run --no-default-browser-check --disable-session-crashed-bubble \
  --disable-features=Translate --overscroll-history-navigation=0 --ozone-platform="$ozone" \
  --user-data-dir="$profile" --disk-cache-size=1 --media-cache-size=1 "$url" & browser_pid=$!
# A server crash must restart the whole kiosk rather than leaving stale content on screen.
while kill -0 "$browser_pid" 2>/dev/null; do
  if [[ -n $server_pid ]] && ! kill -0 "$server_pid" 2>/dev/null; then
    echo "Local dashboard server exited." >&2; exit 1
  fi
  sleep 1
done
wait "$browser_pid"
