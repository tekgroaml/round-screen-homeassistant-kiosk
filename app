#!/bin/sh
# Distribution Python sees the GTK/WebKit packages installed by APT.
set -eu
export PYTHONPATH="$(dirname -- "$0")${PYTHONPATH:+:$PYTHONPATH}"
if [ "$(uname -s)" = Linux ]; then
    exec /usr/bin/python3 -m orbit_app.cli "$@"
fi
exec python3 -m orbit_app.cli "$@"
