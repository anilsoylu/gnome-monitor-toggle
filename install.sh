#!/usr/bin/env bash
# Install gnome-monitor-toggle for the current user.
#
#   ./install.sh             CLI + app
#   ./install.sh --desktop   also put a launcher on the desktop
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HOME}/.local/bin"
DATA="${XDG_DATA_HOME:-${HOME}/.local/share}"
APPS="${DATA}/applications"
LOCALE="${DATA}/locale"
APP_ID="io.github.anilsoylu.MonitorToggle"

# --- dependencies ------------------------------------------------------------
if ! python3 -c "import gi; gi.require_version('Gio', '2.0')" >/dev/null 2>&1; then
  echo "Error: python3-gi was not found." >&2
  echo "       sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" >&2
  exit 1
fi
app=1
if ! check="$(python3 "$HERE/monitor-ui" --check 2>&1)"; then
  app=0
  echo "Warning: installing the monitor command only; the app cannot run here." >&2
  echo "         ${check##*$'\n'}" >&2
  echo "         It needs: sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1 (GNOME 47 or newer)" >&2
fi

# --- install -----------------------------------------------------------------
install -d "$BIN" "$APPS"
install -m 755 "$HERE/monitorctl.py" "$HERE/monitor" "$BIN/"
python3 "$HERE/po/compile-translations.py" "$LOCALE" >/dev/null

if [[ $app == 1 ]]; then
  install -m 755 "$HERE/monitor-ui" "$BIN/"
  sed "s|@EXEC@|${BIN}/monitor-ui|g" "$HERE/monitor-toggle.desktop.in" > "$APPS/${APP_ID}.desktop"
  chmod 644 "$APPS/${APP_ID}.desktop"
fi

if [[ $app == 1 && "${1:-}" == "--desktop" ]]; then
  DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "${HOME}/Desktop")"
  install -d "$DESK"
  install -m 755 "$APPS/${APP_ID}.desktop" "$DESK/"
  gio set "$DESK/${APP_ID}.desktop" metadata::trusted true 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" 2>/dev/null || true
fi

echo "Installed."
[[ $app == 1 ]] && echo "  App: Activities → \"Monitor Toggle\" (or run: monitor-ui)"
echo "  CLI: monitor list | monitor off DP-1 | monitor only DP-1 | monitor on"
