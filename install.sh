#!/bin/sh
# Register Grok Corner with this user: app launcher, autostart, icon, and command.
set -eu
APP=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP"
exec python3 -c 'from pathlib import Path; import prefs; prefs.install(Path(".").resolve())'
