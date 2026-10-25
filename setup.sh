#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -s) == Linux ]] || { echo "Install on Raspberry Pi OS / Debian Linux." >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo "Run as the desktop user; sudo is only used for missing APT packages." >&2; exit 1; }
mode=${1:---install-only}
[[ $mode == --install-only || $mode == --legacy-browser ]] || { echo "Usage: ./setup.sh [--install-only|--legacy-browser]" >&2; exit 2; }
packages=(python3 python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 wlr-randr)
if [[ $mode == --legacy-browser ]]; then packages+=(chromium unclutter); fi
missing=()
for package in "${packages[@]}"; do
  status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)
  [[ $status == 'install ok installed' ]] || missing+=("$package")
done
if ((${#missing[@]})); then
  sudo apt-get update
  sudo apt-get install -y "${missing[@]}"
else
  echo "All native Python/GTK/Cairo dependencies are already installed. No download needed."
fi
echo "Installed. Run ./app check/start with --port 1 or 2 --shape round --panels 1 --input touch."
