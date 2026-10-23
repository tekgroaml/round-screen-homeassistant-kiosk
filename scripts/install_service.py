#!/usr/bin/env python3
"""Install a user service with a desktop-session environment bridge."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def quoted(value, command=False):
    value = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--uninstall", action="store_true")
    a = p.parse_args()
    if os.geteuid() == 0: p.exit(1, "Run as the desktop user without sudo.\n")
    if any(c in str(ROOT) for c in '\n\r\t'): p.exit(1, "Repository path must not contain control characters.\n")
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))
    unit = config/"systemd/user/round-display-kiosk.service"
    autostart = config/"autostart/round-display-kiosk.desktop"
    environment = config/"round-display-kiosk/environment"
    if a.uninstall:
        subprocess.run(["systemctl", "--user", "stop", "round-display-kiosk.service"], check=False)
        unit.unlink(missing_ok=True); autostart.unlink(missing_ok=True)
    else:
        for path in (unit, autostart, environment): path.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(f"""[Unit]
Description=Round display Chromium kiosk
After=graphical-session.target
PartOf=graphical-session.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory={quoted(ROOT)}
EnvironmentFile=-{quoted(environment)}
ExecStart={quoted(ROOT/'scripts/start_kiosk.sh', command=True)}
Restart=always
RestartSec=5
TimeoutStopSec=15
KillMode=control-group
UMask=0077
""")
        # Desktop Exec quoting has a second backslash-escaping layer.
        desktop_command = str(ROOT/'scripts/start_session.sh').replace('\\', '\\\\\\\\').replace('"', '\\\\"').replace('`', '\\\\`').replace('$', '\\\\$').replace('%', '%%')
        autostart.write_text(f"""[Desktop Entry]
Type=Application
Name=Round Display Kiosk
Exec="{desktop_command}"
Terminal=false
X-GNOME-Autostart-enabled=true
""")
        if not environment.exists():
            environment.write_text('# Systemd EnvironmentFile syntax, not a shell script.\nKIOSK_PORT=8765\n# KIOSK_URL=https://homeassistant.local:8123/lovelace/climate\n')
        environment.chmod(0o600)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    if not a.uninstall and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        subprocess.run([str(ROOT/"scripts/start_session.sh")], check=True)
    print("User service removed; environment file retained." if a.uninstall else f"Service installed. Desktop login starts it. Configuration: {environment}")


if __name__ == "__main__": main()
