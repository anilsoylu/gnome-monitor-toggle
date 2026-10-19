#!/usr/bin/env bash
# gnome-monitor-toggle kurulum betiği
#
#   ./install.sh             CLI + arayüz
#   ./install.sh --desktop   ayrıca masaüstüne kısayol koy
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HOME}/.local/bin"
APPS="${HOME}/.local/share/applications"
APP_ID="io.github.anilsoylu.MonitorToggle"

# --- bağımlılık kontrolü -----------------------------------------------------
if ! python3 -c "import gi; gi.require_version('Gio','2.0')" >/dev/null 2>&1; then
  echo "Hata: python3-gi bulunamadı."
  echo "      sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
  exit 1
fi

# --- kurulum -----------------------------------------------------------------
install -d "$BIN" "$APPS"
install -m 755 "$HERE/monitorctl.py" "$HERE/monitor" "$HERE/monitor-ui" "$BIN/"

sed "s|@EXEC@|${BIN}/monitor-ui|g" \
  "$HERE/monitor-toggle.desktop.in" > "$APPS/${APP_ID}.desktop"
chmod 644 "$APPS/${APP_ID}.desktop"

if [[ "${1:-}" == "--desktop" ]]; then
  DESK="${XDG_DESKTOP_DIR:-${HOME}/Desktop}"
  install -d "$DESK"
  cp "$APPS/${APP_ID}.desktop" "$DESK/"
  chmod +x "$DESK/${APP_ID}.desktop"
  gio set "$DESK/${APP_ID}.desktop" metadata::trusted true 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" 2>/dev/null || true
fi

echo "Kuruldu ✓"
echo "  Arayüz : Uygulamalar → \"Monitör Aç/Kapat\"  (veya: monitor-ui)"
echo "  CLI    : monitor list | monitor off DP-1 | monitor on"
