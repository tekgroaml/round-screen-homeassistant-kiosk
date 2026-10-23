#!/usr/bin/env bash
set -euo pipefail
# Called by desktop autostart only after the compositor has created its sockets.
[[ -n ${WAYLAND_DISPLAY:-}${DISPLAY:-} ]] || { echo "No graphical session is available." >&2; exit 1; }
variables=()
for variable in DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS XDG_SESSION_TYPE; do
  if printenv "$variable" >/dev/null; then variables+=("$variable"); else systemctl --user unset-environment "$variable"; fi
done
systemctl --user import-environment "${variables[@]}"
exec systemctl --user restart round-display-kiosk.service
