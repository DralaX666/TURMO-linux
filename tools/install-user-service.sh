#!/usr/bin/env bash
#
# Install TURMO as a per-user systemd service (no root service, no /opt copy).
# Re-run it if the project directory moves.
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT="${UNIT_DIR}/turmo-display.service"
UDEV_SRC="${PROJECT_DIR}/udev/99-turmo-display.rules"
UDEV_DST="/etc/udev/rules.d/99-turmo-display.rules"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now turmo-display.service >/dev/null 2>&1 || true
    rm -f "${UNIT}"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    echo "User service removed. The udev rule was kept."
    exit 0
fi

if systemctl is-active --quiet turmo-display.service 2>/dev/null; then
    echo "A system-wide turmo-display.service is active."
    echo "Disable it first: sudo systemctl disable --now turmo-display"
    exit 1
fi

if [ -x "${PROJECT_DIR}/.venv/bin/python" ]; then
    PYTHON="${PROJECT_DIR}/.venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

if ! "${PYTHON}" -c "import serial, PIL, numpy" >/dev/null 2>&1; then
    echo "Missing Python dependencies for ${PYTHON}."
    echo "Run: ${PYTHON} -m pip install -r ${PROJECT_DIR}/requirements.txt"
    echo "Or create a virtual environment first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "${UDEV_DST}" ] || ! cmp -s "${UDEV_SRC}" "${UDEV_DST}"; then
    echo "==> Installing udev rule (sudo required)"
    if sudo install -m 644 "${UDEV_SRC}" "${UDEV_DST}"; then
        sudo udevadm control --reload-rules
        sudo udevadm trigger
    else
        echo "Warning: udev rule was not installed."
        echo "         The display may still work as /dev/ttyACM0."
        echo "         To install it later: sudo install -m 644 ${UDEV_SRC} ${UDEV_DST}"
    fi
fi

echo "==> Writing ${UNIT}"
mkdir -p "${UNIT_DIR}"
cat > "${UNIT}" <<EOF
[Unit]
Description=TURMO Smart Screen Dashboard
[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON} -m turmo_display.app
Environment=PYTHONPATH=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now turmo-display.service

if command -v loginctl >/dev/null 2>&1; then
    if [ "$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)" != "yes" ]; then
        echo "==> Enabling linger so the service starts at boot (sudo required)"
        sudo loginctl enable-linger "${USER}" || echo "Could not enable linger; the service will start at login."
    fi
fi

sleep 2
if systemctl --user is-active --quiet turmo-display.service; then
    echo
    echo "✔ TURMO user service is running."
else
    echo
    echo "⚠ Service installed but not active yet."
    echo "  Check: journalctl --user -u turmo-display -n 50 --no-pager"
fi

echo
echo "Control panel : http://localhost:8777"
echo "Status        : systemctl --user status turmo-display"
echo "Logs          : journalctl --user -u turmo-display -f"
echo "Config        : ${PROJECT_DIR}/config.json"
echo "Desktop icon  : ${PROJECT_DIR}/tools/install-desktop-shortcut.sh"
