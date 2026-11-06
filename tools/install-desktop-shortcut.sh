#!/usr/bin/env bash
#
# Install a "TURMO Control" shortcut on the desktop and in the application menu.
# Re-run it if the project directory moves.
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="${PROJECT_DIR}/tools/turmo-desktop.sh"
ICON="${PROJECT_DIR}/docs/icon.png"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-${HOME}/Desktop}"
APPS_DIR="${HOME}/.local/share/applications"

if [ ! -x "${HELPER}" ]; then
    chmod +x "${HELPER}"
fi

desktop_entry() {
    cat <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=TURMO Control
Comment=Open the TURMO dashboard control panel
Exec="${HELPER}" open
Icon=${ICON}
Terminal=false
Categories=System;Monitor;
Keywords=turmo;display;dashboard;
StartupNotify=false
Actions=Open;Edit;Restart;Stop;

[Desktop Action Open]
Name=Open control panel
Exec="${HELPER}" open

[Desktop Action Edit]
Name=Edit config.json
Exec="${HELPER}" edit

[Desktop Action Restart]
Name=Restart service
Exec="${HELPER}" restart

[Desktop Action Stop]
Name=Stop control panel
Exec="${HELPER}" stop
EOF
}

install_one() {
    local target="$1"
    mkdir -p "$(dirname "${target}")"
    desktop_entry > "${target}"
    chmod +x "${target}"
    if command -v gio >/dev/null 2>&1; then
        gio set "${target}" metadata::trusted true >/dev/null 2>&1 || true
    fi
    echo "Installed: ${target}"
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "${DESKTOP_DIR}/TURMO Control.desktop" "${APPS_DIR}/turmo-control.desktop"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${APPS_DIR}" >/dev/null 2>&1 || true
    echo "TURMO shortcut removed."
    exit 0
fi

install_one "${DESKTOP_DIR}/TURMO Control.desktop"
install_one "${APPS_DIR}/turmo-control.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" >/dev/null 2>&1 || true
fi

echo
echo "Shortcut ready. Right-click it for: Open control panel, Edit config.json, Restart service, Stop control panel."
