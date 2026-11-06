#!/usr/bin/env bash
#
# Small helper used by the desktop shortcut.
#   turmo-desktop.sh open     start the display service (if needed), start the
#                             on-demand editor and open it in the browser
#   turmo-desktop.sh edit     open config.json in the default editor
#   turmo-desktop.sh restart  restart the display service
#   turmo-desktop.sh stop     stop the on-demand editor
#
set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${PROJECT_DIR}/config.json"
PYTHON="${PROJECT_DIR}/.venv/bin/python"
if [ ! -x "${PYTHON}" ]; then
    PYTHON="$(command -v python3)"
fi
CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}"
LOG_FILE="${CACHE_DIR}/turmo-webapp.log"
PID_FILE="${CACHE_DIR}/turmo-webapp.pid"
PORT="$("${PYTHON}" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("web_port", 8777))' "${CONFIG}" 2>/dev/null || echo 8777)"
URL="http://127.0.0.1:${PORT}"

gui_running() {
    curl -fsS --max-time 1 "${URL}/api/state" >/dev/null 2>&1
}

open_panel() {
    # The display service is permanent; starting it again is harmless.
    systemctl --user start turmo-display.service >/dev/null 2>&1 || true

    if ! gui_running; then
        mkdir -p "${CACHE_DIR}"
        (
            cd "${PROJECT_DIR}" || exit 1
            nohup "${PYTHON}" -m turmo_display.webapp --config "${CONFIG}" \
                >>"${LOG_FILE}" 2>&1 &
            echo $! > "${PID_FILE}"
        )
    fi

    if command -v curl >/dev/null 2>&1; then
        for _ in $(seq 1 20); do
            if gui_running; then
                break
            fi
            sleep 0.25
        done
    else
        sleep 1
    fi

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${URL}" >/dev/null 2>&1 &
    elif [ -n "${BROWSER:-}" ]; then
        "${BROWSER}" "${URL}" >/dev/null 2>&1 &
    else
        echo "Open ${URL} in your browser."
    fi
}

case "${1:-open}" in
    open)
        open_panel
        ;;
    edit)
        if [ ! -f "${CONFIG}" ]; then
            cp "${PROJECT_DIR}/config.example.json" "${CONFIG}"
        fi
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "${CONFIG}" >/dev/null 2>&1 &
        else
            echo "${CONFIG}"
        fi
        ;;
    restart)
        systemctl --user restart turmo-display.service
        if command -v notify-send >/dev/null 2>&1; then
            notify-send "TURMO" "Display service restarted" >/dev/null 2>&1 || true
        fi
        ;;
    stop)
        if command -v curl >/dev/null 2>&1; then
            curl -fsS -X POST "${URL}/api/shutdown?force=1" >/dev/null 2>&1 || true
        fi
        rm -f "${PID_FILE}"
        ;;
    *)
        echo "Usage: $0 {open|edit|restart|stop}" >&2
        exit 2
        ;;
esac
