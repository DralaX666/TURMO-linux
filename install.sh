#!/usr/bin/env bash
#
# Install the TURMO / Turing Smart Screen BLACKBOX dashboard on Ubuntu.
# Run from the directory that contains this file:
#     sudo ./install.sh
#
set -euo pipefail

APP_DIR="/opt/turmo-display"
CONF_DIR="/etc/turmo-display"
SERVICE="/etc/systemd/system/turmo-display.service"
UDEV="/etc/udev/rules.d/99-turmo-display.rules"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${EUID}" -ne 0 ]; then
    echo "Error: run with sudo (e.g. sudo ./install.sh)" >&2
    exit 1
fi

if [ ! -d "${SRC_DIR}/turmo_display" ]; then
    echo "Error: turmo_display/ not found next to install.sh" >&2
    exit 1
fi

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Copying the program to ${APP_DIR}"
mkdir -p "${APP_DIR}" "${CONF_DIR}"
systemctl stop turmo-display 2>/dev/null || true
rm -rf "${APP_DIR}/turmo_display" "${APP_DIR}/tools"
cp -r "${SRC_DIR}/turmo_display" "${APP_DIR}/turmo_display"
if [ -d "${SRC_DIR}/tools" ]; then
    cp -r "${SRC_DIR}/tools" "${APP_DIR}/tools"
fi
cp "${SRC_DIR}/requirements.txt" "${APP_DIR}/requirements.txt"

echo "==> Creating the Python environment"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

if [ ! -f "${CONF_DIR}/config.json" ]; then
    echo "==> Creating the default configuration"
    cp "${SRC_DIR}/config.example.json" "${CONF_DIR}/config.json"
else
    echo "==> Keeping the existing configuration ${CONF_DIR}/config.json"
fi

echo "==> Installing the udev rule"
install -m 644 "${SRC_DIR}/udev/99-turmo-display.rules" "${UDEV}"
udevadm control --reload-rules || true
udevadm trigger || true

echo "==> Installing the systemd service"
install -m 644 "${SRC_DIR}/systemd/turmo-display.service" "${SERVICE}"
systemctl daemon-reload
systemctl enable turmo-display >/dev/null
systemctl restart turmo-display

sleep 2
if systemctl is-active --quiet turmo-display; then
    echo
    echo "✔ Installed. The service is running."
else
    echo
    echo "⚠ The service started but is not active right now."
    echo "  Check: journalctl -u turmo-display -n 50 --no-pager"
fi

echo
echo "Configuration : ${CONF_DIR}/config.json"
echo "Status        : systemctl status turmo-display"
echo "Logs          : journalctl -u turmo-display -f"
echo "Restart       : sudo systemctl restart turmo-display"
echo "Preview image : ${APP_DIR}/venv/bin/python -m turmo_display --preview /tmp/blackbox.png"
