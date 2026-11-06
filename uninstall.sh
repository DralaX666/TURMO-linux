#!/usr/bin/env bash
#
# Uninstall the TURMO / Turing Smart Screen dashboard.
#     sudo ./uninstall.sh
#
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
    echo "Error: run with sudo" >&2
    exit 1
fi

systemctl stop turmo-display 2>/dev/null || true
systemctl disable turmo-display 2>/dev/null || true
rm -f /etc/systemd/system/turmo-display.service
rm -f /etc/udev/rules.d/99-turmo-display.rules
systemctl daemon-reload
udevadm control --reload-rules || true
rm -rf /opt/turmo-display

echo "Removed (the configuration in /etc/turmo-display was kept)."
echo "To remove it as well: sudo rm -rf /etc/turmo-display"
