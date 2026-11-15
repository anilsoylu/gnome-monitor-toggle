#!/usr/bin/env bash
# Remove gnome-monitor-toggle for the current user. The saved layout is kept.
set -euo pipefail

BIN="${HOME}/.local/bin"
DATA="${XDG_DATA_HOME:-${HOME}/.local/share}"
APPS="${DATA}/applications"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "${HOME}/Desktop")"
STATE="${XDG_STATE_HOME:-${HOME}/.local/state}/monitor-toggle"
APP_ID="io.github.anilsoylu.MonitorToggle"

rm -f "$BIN/monitorctl.py" "$BIN/monitor" "$BIN/monitor-ui"
rm -f "$APPS/${APP_ID}.desktop" "$DESK/${APP_ID}.desktop"
rm -f "$DATA"/locale/*/LC_MESSAGES/monitor-toggle.mo

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" 2>/dev/null || true
fi

echo "Removed. Saved layout and settings are kept in ${STATE}/ (delete that folder to remove them)."
