#!/usr/bin/env bash
# Run a command inside a private D-Bus session next to a headless Mutter.
#
#   tests/run-headless.sh python3 -m unittest discover -s tests
#
# VIRTUAL_MONITORS overrides the virtual monitor list (space separated WxH@R).
set -euo pipefail

if [[ "${GMT_IN_SESSION:-}" != 1 ]]; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
  mkdir -p -m 700 "$XDG_RUNTIME_DIR"
  exec env GMT_IN_SESSION=1 dbus-run-session -- "$0" "$@"
fi

monitors=()
for m in ${VIRTUAL_MONITORS:-1920x1080@60 1920x1080@144 1280x1024@60}; do
  monitors+=(--virtual-monitor "$m")
done

mutter --wayland --headless --no-x11 "${monitors[@]}" >"$XDG_RUNTIME_DIR/mutter.log" 2>&1 &
mutter_pid=$!
trap 'kill "$mutter_pid" 2>/dev/null || true' EXIT

for _ in $(seq 50); do
  if gdbus introspect --session --dest org.gnome.Mutter.DisplayConfig \
      --object-path /org/gnome/Mutter/DisplayConfig >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

export WAYLAND_DISPLAY=wayland-0 GDK_BACKEND=wayland GTK_A11Y=none
"$@"
