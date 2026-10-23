#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -s) == Linux ]] || { echo "This installer requires Raspberry Pi OS or Debian Linux." >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo "Run as the desktop user; sudo is used only for APT." >&2; exit 1; }
sudo apt-get update
sudo apt-get install -y python3 unclutter
if apt-cache show chromium >/dev/null 2>&1; then sudo apt-get install -y chromium
else sudo apt-get install -y chromium-browser; fi
if [[ ${1:-} == --install-only ]]; then exit 0; fi
exec ./scripts/start_kiosk.sh
