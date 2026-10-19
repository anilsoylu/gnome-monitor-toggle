#!/usr/bin/env bash
# gnome-monitor-toggle kaldırma betiği
set -euo pipefail

BIN="${HOME}/.local/bin"
APPS="${HOME}/.local/share/applications"
DESK="${XDG_DESKTOP_DIR:-${HOME}/Desktop}"
APP_ID="io.github.anilsoylu.MonitorToggle"

rm -f "$BIN/monitorctl.py" "$BIN/monitor" "$BIN/monitor-ui"
rm -f "$APPS/${APP_ID}.desktop" "$DESK/${APP_ID}.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" 2>/dev/null || true
fi

echo "Kaldırıldı. (Kayıtlı düzen: ~/.cache/monitor-toggle.json)"
