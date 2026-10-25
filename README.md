# Orbit — native Python circular touchscreen dashboard

**v0.3.0** draws directly with Python, GTK3 and Cairo. The standard ./app path needs no browser, WebKit, HTTP server, pip, Node or virtual environment. It runs independently of pi-setting.

![Native Python circular dashboard](docs/previews/native-800.png)
[中文](README_CN.md) · [Copy to Pi and run over SSH](docs/raspberry-pi-ssh_EN.md) · [Command details](docs/standard-app.md) · [Verification](docs/verification.md)

## Start on a configured touchscreen

On Raspberry Pi OS Bookworm Desktop/labwc, as the ordinary logged-in desktop user:

```bash
./setup.sh --install-only
./app check --port 2 --shape round --panels 1 --input touch
./app start --port 2 --shape round --panels 1 --input touch --data-source demo
./app status --port 2
./app logs --port 2 --follow
./app stop --port 2
```

Port 1 means HDMI-A-1/Pi4 board HDMI0; port 2 means HDMI-A-2/board HDMI1. Change every port argument together. A square canvas >=360×360, scale 100% and normal rotation are required. No display timing or USB mapping is changed. SSH discovers the same user's unique Wayland desktop; a console-only login is insufficient.

The installer checks distribution Python/GTK/Cairo/layer-shell/wlr-randr packages and only downloads missing dependencies. It does not launch a browser or install new autostart. start runs in the background while the desktop remains logged in. Logs Ctrl+C only stops following logs.

## Touch and data

Tap−/+ for 0.5°C steps or drag the dial ring (16–30°C). Labels do not modify temperature. One contact owns a gesture; cancelled gestures and releases outside buttons do not write. Native touch and emulated pointer input are handled without duplicate commits.

The tested 800×800@60 configuration on HDMI-A-2 displayed correctly; the user confirmed buttons and ring drag, and native touch events were observed. This does not certify other products, live HA integration or long-duration behavior.

Demo uses in-process Python data, ignoring inherited HA credentials. Live uses --data-source live --config <file> with examples/homeassistant.json and an owner-private token_file (0600). Tokens never enter command arguments or logs. Relative token paths resolve beside the configuration file. Data reads/writes run outside the GTK thread; errors do not silently fall back to demo.

Standard actions remain info/check/run/start/status/logs/restart/stop, plus --help/--version. Own-instance replacement supports rollback; other app owners are not killed. Tests cover contract rejection, demo/live isolation, HTTP HA fixtures, geometry, locks, ownership and native gestures.

## Structure and legacy paths

orbit_app/drawing.py and touch.py share rendering/hit geometry; worker.py owns the GTK surface; backend.py is a standard-library adapter; cli.py/runtime.py provide command lifecycle. The legacy ui/, server.py and Chromium scripts remain separate and are not invoked by ./app. Optional browser dependencies require explicit ./setup.sh --legacy-browser.

If the old round-display-kiosk.service is active, migrate it with ./scripts/install_service.sh --uninstall first. There is no new reboot autostart. See the self-contained deployment guide for copying the entire project, dependencies and SSH management.
