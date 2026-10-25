# Copy Orbit to a Raspberry Pi and operate it over SSH

[中文](raspberry-pi-ssh.md) · [Project README](../README.md)

This is a self-contained deployment guide. You copy application files into the Pi user's home directory; you do not reflash the operating-system card. No parent application repository, pi-setting or global screen-app installation is required.

## Prerequisites and terminal locations

Use Raspberry Pi OS Bookworm 64-bit Desktop with that user already logged into labwc/Wayland. SSH or a console login alone does not create a graphical session. Enable SSH and connect the Mac and Pi to a reachable network.

Configure a stable square canvas of at least 360×360,100% desktop scale and normal output rotation. Connect the touchscreen's USB data cable and verify its mapping independently. System/vendor configuration is sufficient; screen-config/screen-test are optional.

Commands below use pi@raspberrypi.local as an example: replace both the username and hostname/IP with your deployment. Verify the host fingerprint and authenticate using SSH normally; do not embed a password in these commands.

## 1. Mac terminal: upload the entire project

On the Mac, enter the directory containing the round-screen-homeassistant-kiosk folder:

```bash
ssh pi@raspberrypi.local 'mkdir -p ~/apps/round-screen-homeassistant-kiosk'
rsync -av --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=secrets --exclude=ha-token round-screen-homeassistant-kiosk/ pi@raspberrypi.local:~/apps/round-screen-homeassistant-kiosk/
ssh pi@raspberrypi.local
```

The source trailing slash copies the folder contents. Upload the entire project, especially app, orbit_app and screen-app.json. The standard native renderer does not load the legacy HTML or HTTP server. Keep private HA configuration outside the published source, for example under ~/.config/orbit on the Pi.

Only published GitHub changes can be obtained by clone/pull. As an alternative to the upload, after installing git on the Pi, clone the published repository into a nonexistent target directory:

```bash
sudo apt-get update
sudo apt-get install -y git
mkdir -p ~/apps
git clone https://github.com/tekgroaml/round-screen-homeassistant-kiosk.git ~/apps/round-screen-homeassistant-kiosk
```

Use one deployment method. Local unpublished modifications require the upload path.

## 2. Pi SSH terminal: install

After the SSH login, execute on the Pi:

```bash
cd ~/apps/round-screen-homeassistant-kiosk
chmod +x app setup.sh scripts/*.sh
./setup.sh --install-only
./app --version
./app info --json
```

The installer uses sudo for APT and needs access to package repositories. Run app as the ordinary desktop user, without sudo. The native installer only installs missing packages and never launches a browser.

## 3. Pi SSH terminal: check and start

```bash
./app check --port 1 --shape round --panels 1 --input touch
./app start --port 1 --shape round --panels 1 --input touch --data-source demo
```

Port 1 is HDMI-A-1/Pi4 board HDMI0, nearest USB-C. Port 2 is HDMI-A-2/board HDMI1. Change every --port consistently if using the second connector.

The app discovers this user's unique Wayland socket. No SSH X-forwarding or guessed DISPLAY=:0 is needed. With multiple graphical sessions, list real sockets and explicitly select the intended one:

```bash
python3 - <<'PY'
import os
from pathlib import Path
for item in sorted((Path('/run/user') / str(os.getuid())).glob('wayland-*')):
    if item.is_socket():
        print(item.name)
PY
```

Set, for example, export WAYLAND_DISPLAY=wayland-0 only if that is the actual intended socket. If none exists, log into the Pi desktop first. Demo does not require Home Assistant and ignores inherited HA credentials.

## 4. Manage it and disconnect SSH

To manually test colors/touch before the demo, use the optional screen-test tool if already installed. This example uses connector 2; change every number together for connector 1:

```bash
cd ~/apps/round-screen-homeassistant-kiosk
./app stop --port 2
screen-test tap-cycle --screen 2
```

Tap the physical screen and observe the color changes. Only after finishing that manual check, execute:

```bash
screen-test stop --screen 2
./app start --port 2 --shape round --panels 1 --input touch --data-source demo
./app status --port 2
```

Stop the current program before switching. screen-test is optional, not a runtime dependency. Do not paste both blocks together and skip the manual observation.

```bash
./app status --port 1
./app logs --port 1 --follow
```

Ctrl+C exits log following only. Then:

```bash
./app restart --port 1
./app stop --port 1
```

start creates a supervised background instance and waits for readiness. It can remain running after SSH disconnects while the desktop session remains logged in. Log in again and enter the same project directory to control it.

For foreground debugging, stop the background instance and use ./app run with the same launch parameters; Ctrl+C ends the foreground run. Foreground run is not the persistent SSH-disconnect method. This release does not automatically install autostart or promise recovery after a Pi reboot/desktop logout.

## 5. Update and diagnose

Stop the instance on the Pi before uploading changed files. Repeat rsync from the Mac, reinstall if dependencies changed, then check ./app --version, run check and start. Do not replace running source and assume an old binary can be rolled back.

- No desktop/session: use the same user that owns the logged-in Wayland desktop.
- Missing Python GTK/Cairo/wlr-randr: run the Pi installer; the native launcher is not a Mac/X11 application.
- Unsupported canvas: configure the correct mode, scale and rotation before launching.
- Permission denied: restore executable bits and user ownership; do not solve it by running the app with sudo.
- Legacy kiosk service active: migrate with ./scripts/install_service.sh --uninstall. Its private environment file is retained.
- Optional screen-test occupies the output: stop that test first.
- Touch offsets/cross-output events: verify USB mapping and physical positions separately. Event counters are not calibration proof.

For private HA token_file configuration and explicit live mode, see the project README. The native 800×800@60 demo on HDMI-A-2 was verified on Pi and the user confirmed complete rendering, buttons and dial touch. Other products, live HA and long-duration behavior need separate acceptance.
