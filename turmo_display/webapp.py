"""On-demand web editor for the TURMO dashboard.

This process is deliberately separate from the display service:

* ``turmo-display`` keeps the serial port and updates the screen continuously.
* ``turmo_display.webapp`` starts only when you want to edit settings, writes
  ``config.json`` and shuts down after a period of inactivity (or via the
  "Stop control panel" button).

The editor is local-only and binds to 127.0.0.1.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from .app import config_write_path, load_config_with_path
from .lcd import find_port
from .render import Renderer
from .runtime import RuntimeConfig
from .stats import DemoSampler, Sampler
from .webui import start_web_server

log = logging.getLogger("turmo.webapp")

DEFAULT_IDLE_TIMEOUT = 20


def _truthy(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(value)


def _dimensions(config: dict):
    try:
        orientation = int(config.get("orientation", 0))
    except (TypeError, ValueError):
        orientation = 0
    return (480, 320) if orientation in (1, 2, 3) else (320, 480)


def _update_status(runtime: RuntimeConfig, config: dict) -> None:
    port = find_port()
    width, height = _dimensions(config)
    runtime.set_status(
        connected=bool(port),
        model="Turing Smart Screen 3.5" if port else None,
        width=width if port else None,
        height=height if port else None,
        port=port,
        last_error=None if port else "Display not found on USB",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="turmo_display.webapp",
        description="On-demand local control panel for the TURMO dashboard",
    )
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--port", type=int, help="local port (default: web_port in config, 8777)")
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT,
        help="stop after N seconds without requests (0 = never)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use demo statistics for the preview (screenshots/development)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    config, used_path = load_config_with_path(args.config)
    config_path = config_write_path(args.config, used_path)
    try:
        port = args.port if args.port is not None else int(config.get("web_port", 8777))
    except (TypeError, ValueError):
        port = 8777
    runtime = RuntimeConfig(config, config_path)
    _update_status(runtime, config)

    sampler = DemoSampler() if args.demo else Sampler()
    sampler.sample()  # prime rate calculations
    preview_lock = threading.Lock()

    def render_preview():
        with preview_lock:
            current = runtime.snapshot()
            stats = sampler.sample()
            if not _truthy(current.get("show_gpu", True)):
                stats.gpu = None
            width, height = _dimensions(current)
            image = Renderer(width, height, current.get("hostname") or "", current).render(stats)
            runtime.set_frame(image)
            _update_status(runtime, current)
            return image

    stop_event = threading.Event()
    client_lock = threading.Lock()
    client_count = 0
    disconnect_timer = None

    def on_client_change(connected):
        nonlocal client_count, disconnect_timer
        with client_lock:
            if connected:
                client_count += 1
                if disconnect_timer is not None:
                    disconnect_timer.cancel()
                    disconnect_timer = None
                log.info("Browser connected")
            else:
                client_count = max(0, client_count - 1)
                if client_count == 0:
                    log.info("Browser disconnected; stopping soon")
                    disconnect_timer = threading.Timer(3.0, stop_event.set)
                    disconnect_timer.daemon = True
                    disconnect_timer.start()

    def request_stop():
        if runtime.force_shutdown_requested():
            stop_event.set()
            return
        # Closing the tab sends a beacon. Wait a few seconds so a reload can
        # cancel the shutdown by making a fresh request.
        time.sleep(3)
        if runtime.shutdown_pending():
            stop_event.set()
        else:
            log.info("Shutdown cancelled by new activity")

    server = start_web_server(
        runtime,
        "127.0.0.1",
        port,
        preview_provider=render_preview,
        on_shutdown=request_stop,
        on_client_change=on_client_change,
    )
    if server is None:
        log.error("Could not start the control panel on 127.0.0.1:%s", port)
        return 1

    def _stop(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    def idle_monitor():
        if args.idle_timeout <= 0:
            return
        while not stop_event.wait(5):
            if runtime.idle_seconds() > args.idle_timeout:
                log.info("No activity for %s s; stopping the control panel", args.idle_timeout)
                stop_event.set()
                return

    threading.Thread(target=idle_monitor, name="turmo-web-idle", daemon=True).start()

    log.info("Control panel: http://127.0.0.1:%s", server.server_address[1])
    log.info("Config: %s", config_path)
    log.info("Close the page or use the Stop button; idle timeout is %s s", args.idle_timeout)

    stop_event.wait()

    def force_exit():
        time.sleep(3)
        log.warning("Forcing editor exit")
        os._exit(0)

    threading.Thread(target=force_exit, name="turmo-web-force-exit", daemon=True).start()
    server.shutdown()
    server.server_close()
    log.info("Control panel stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
