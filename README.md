# Orbit — Round Home Assistant Kiosk

![UI](https://img.shields.io/badge/UI-HTML%20%2F%20CSS%20%2F%20JS-orange) ![Runtime](https://img.shields.io/badge/runtime-Chromium%20%2B%20Python%203.9%2B-blue) ![Autostart](https://img.shields.io/badge/autostart-systemd-green)

[简体中文](README_CN.md)

A circular climate dashboard with a warm metallic dial, temperature, humidity, local clock, weather and a touch/keyboard rotary setpoint. All content is clipped to the visible circle. Works at 480×480 and 720×720 without external fonts, frameworks or cloud assets. Demo telemetry is explicitly labeled; optional Home Assistant REST integration runs behind a loopback-only Python adapter so its token never reaches browser JavaScript.

![Software preview](docs/preview.png)

## Files

```text
round-screen-homeassistant-kiosk/
├── docs/
│   └── preview.png
├── scripts/
│   ├── install_service.py
│   ├── install_service.sh
│   ├── start_kiosk.sh
│   └── start_session.sh
├── tests/
│   └── test_server.py
├── ui/
│   ├── app.js
│   ├── index.html
│   └── style.css
├── .gitignore
├── README.md
├── README_CN.md
├── server.py
└── setup.sh
```

## Hardware and quick start

Power off first. Connect Pi HDMI0 (micro-HDMI on Pi 4/5) to the controller's HDMI input. Supply the board and Pi according to their labels, and connect the board's USB HID touch/data port with a USB data cable. Configure the desktop to the panel's native 480×480 or 720×720 with 100% scaling using the companion hardware guide. Raspberry Pi OS Bookworm/Bullseye desktop or configured Debian with Chromium and a working Wayland/X11 session is required.

```bash
chmod +x setup.sh scripts/*.sh scripts/*.py
./setup.sh                    # Installs APT dependencies and opens the demo
./setup.sh --install-only     # Install without launching
./scripts/start_kiosk.sh      # Later launches
```

No pip packages or venv are needed: the server uses only Python's standard library. Chromium runs as your desktop user with its sandbox enabled. Wayland uses the native Ozone backend; X11 uses its own backend and `unclutter`. CSS hides the cursor inside the bundled dashboard on both. External HA pages may require the compositor's cursor hiding setting on Wayland. Kiosk mode is a presentation mode, not an OS access-control boundary; Alt+F4 or the desktop window controls can exit it.

Development preview on any machine with Python 3.9+:

```bash
python3 server.py --port 8765
# Open http://127.0.0.1:8765/ in a browser. Do not open index.html as file://.
```

## Dial behavior and API

Drag around the ring to choose 16–30 °C in 0.5 °C steps. Focus the slider and use arrow keys, Home or End for keyboard control. The browser polls telemetry every 10 seconds, updates the clock every second, debounces writes and reports offline/write failures. The screen shows last known telemetry while offline. The Celsius UI is deliberate; Fahrenheit entities are rejected rather than mislabeled. The demo target lives in memory and resets to 22 °C when the server restarts; the clock follows the Pi's locale/time zone, so configure time synchronization first.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/state` | JSON `temperature`, `humidity`, `target`, `weather`, `mode` (`demo` or `homeassistant`) |
| `POST /api/setpoint` | JSON `{"target":22.5}`; returns accepted `target` and `mode` |

```bash
curl http://127.0.0.1:8765/api/state
curl -X POST http://127.0.0.1:8765/api/setpoint \
  -H 'Content-Type: application/json' -d '{"target":22.5}'
```

The server binds **127.0.0.1 only**, checks Host/Origin, sets no-store headers, limits write body size and rejects cross-origin browser writes. No HA token or raw HA payload appears in the UI. Do not expose this development-size adapter with a public port forward. To add another system, implement `Backend.state()` and `Backend.setpoint()` with the same normalized contract. The REST adapter is the integration seam; this project does not implement a WebSocket endpoint.

## Connect the bundled UI to Home Assistant

Create a Home Assistant long-lived token for an appropriately restricted user. Choose a numeric Celsius temperature sensor, a humidity sensor in percent, a single-setpoint Celsius `climate` entity and a weather entity. The climate entity must support `climate.set_temperature`. Temperature unavailable/unknown states produce an explicit API failure. Entity `min_temp`, `max_temp` and `target_temp_step` are checked before a write; adjust both frontend/backend constants if you need a range beyond 16–30 °C. Dual-setpoint heat/cool entities need an adapter change.

For an interactive local launch, export `HA_URL`, `HA_TOKEN`, `HA_TEMP_ENTITY`, `HA_HUMIDITY_ENTITY`, `HA_CLIMATE_ENTITY` and `HA_WEATHER_ENTITY` in your shell, then start the kiosk. For persistent setup, install the service below and edit its private environment file (mode 0600). It uses **systemd EnvironmentFile syntax**, not shell `export` statements. Set each key to your actual HA URL/token/entity ID. Defaults are `sensor.living_room_temperature`, `sensor.living_room_humidity`, `climate.living_room`, `weather.home`. Both `HA_URL` and `HA_TOKEN` must be set together; leaving both unset enables demo mode. Keep tokens out of Git and screenshots.

The server reads `/api/states/{entity_id}` with the Bearer token and sends `/api/services/climate/set_temperature` with `entity_id` and `temperature`. Requests time out, redirects are rejected and HTTPS certificates are validated. Use a valid local CA certificate rather than disabling TLS verification. A successful service call means HA accepted the request, not that physical heating has completed; later polling reports the entity's authoritative setpoint. The adapter does not bypass HA permissions or authenticate users itself.

## Show an existing Lovelace dashboard instead

Set `KIOSK_URL` to your HA dashboard URL, for example `https://homeassistant.local:8123/lovelace/climate`, then launch. This displays the complete HA frontend; the local UI/server is bypassed. Chromium must be able to resolve the host and trust its TLS certificate. Login is performed in the HA UI. The default Chromium profile is temporary and removed on exit, so remote HA login is **not retained** across restarts; use an appropriately managed persistent browser session if that is required. Do not place long-lived tokens in URLs or turn off HA authentication.

Home Assistant Cast is a different path: Lovelace Cast targets a Cast-capable receiver and needs HA's supported HTTPS/network configuration. This Pi runs Chromium locally and is not made into a Google Cast receiver by these scripts. A direct Lovelace URL is the supported Pi path here.

## Boot into the kiosk with systemd

Configure **desktop autologin** using `sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin (menu wording varies). Console autologin alone does not start a compositor. Then run as the desktop user, **without sudo**:

```bash
./scripts/install_service.sh
# Edit ~/.config/round-display-kiosk/environment if using HA or KIOSK_URL.
systemctl --user restart round-display-kiosk.service
systemctl --user status round-display-kiosk.service
journalctl --user -u round-display-kiosk.service -b
```

The installer writes a user service under `$XDG_CONFIG_HOME/systemd/user` (default `~/.config/systemd/user`) and an XDG desktop autostart entry. On login, `start_session.sh` imports the actual DISPLAY/WAYLAND_DISPLAY/session environment, then starts the unit. This avoids guessing `wayland-0` or launching a browser before the compositor is ready. The service restarts failed/exited kiosk processes with a delay and rate limit. It is started by desktop autostart rather than `systemctl enable` or user lingering. Keep the repository at its installed absolute path; rerun the installer after moving it.

The desktop must honor XDG autostart. Raspberry Pi OS sessions normally do; for a custom minimal labwc/Wayfire session that does not, add the absolute `scripts/start_session.sh` command to that compositor's autostart **instead** of the XDG entry. A user service still needs a working user systemd/DBus session. For a clean appliance appearance configure desktop blanking/idle/lock in the desktop settings; these scripts do not globally change power management.

```bash
./scripts/install_service.sh --uninstall
```

Uninstall stops the service and removes its unit/autostart file; your environment file is retained. Desktop autologin remains a system setting you can undo with raspi-config. A temporary Chromium profile and tiny cache limits prevent session/cache persistence; responses from the bundled server use `Cache-Control: no-store`.

## Display boundaries and troubleshooting

The bundled UI is a **single-panel** dashboard. A dual HDMI controller still represents one wide SBS output; it does not become two independent DRM displays. To run two dashboards, extend this page into a `2 × width` by `height` container with two independently clipped square panels, and render each dashboard in its half. This repository does not claim to duplicate the single circle across both halves automatically.

| Problem | Check |
| --- | --- |
| Black browser or no video device | Active desktop, correct HDMI mode, native scaling and user/session permissions; avoid sudo Chromium. |
| Service starts manually but not after boot | Desktop autologin, XDG/compositor autostart and user journal; `start_session.sh` must run after compositor startup. |
| Offline or HA errors | HA base URL, token permissions, actual entity IDs, Celsius units, valid TLS and entity availability. No failure silently falls back to demo mode. |
| Setpoint rejected | 16–30 °C / 0.5 steps, entity range/step and HA service support. |
| Port occupied | Stop another server or set `KIOSK_PORT` to an unused 1024–65535 port. |
| Pointer visible on a remote page | Bundled CSS cannot affect remote origins; use X11 unclutter or the Wayland compositor's cursor settings. |
| UI cut off | Native square resolution, no overscan, 100% scale; circular masking intentionally hides corners. |

## Validation boundary

Local API/mock checks and browser previews verify software behavior. Boot autostart, touch gestures, GPU/compositor behavior and a live HA device still need verification on your actual Pi/network.

## Developer verification

```bash
python3 -m unittest discover -s tests -v
```

The 4 standard-library tests cover the core configuration, behavior or input/API boundary. Home Assistant requests run against a local HTTP fixture, including service payloads, Celsius validation, redirect rejection and local origin checks. The development verification used macOS, not Raspberry Pi hardware. Shell syntax and Python compilation were checked; the interactive demos were rendered where applicable. APT installation and the actual Pi boot/desktop still require on-device checks.
