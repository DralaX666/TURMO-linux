from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import List, Optional, Tuple

from PIL import Image

from .lcd import (
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    TuringRevA,
    find_port,
    list_ports_text,
)
from .render import Renderer
from .stats import DemoSampler, Sampler
from .themes import THEMES, theme_choices

log = logging.getLogger("turmo")

DEFAULT_CONFIG = {
    "port": "auto",
    "baud": 115200,
    "brightness": 85,
    "orientation": 0,
    "refresh_seconds": 1.0,
    "full_refresh_seconds": 30,
    "hostname": "",
    "web_port": 8777,
    "theme": "blackbox",
    "theme_colors": {},
    "title": "BLACKBOX",
    "subtitle": "",
    "footer_text": "TURMO / LINUX",
    "show_gpu": True,
    "show_system": True,
    "show_clock": True,
    "show_cpu": True,
    "show_cpu_temp": True,
    "show_cpu_freq": True,
    "show_cpu_load": True,
    "show_cpu_history": True,
    "show_memory": True,
    "show_swap": True,
    "show_network": True,
    "show_net_totals": True,
    "show_net_history": True,
    "show_gpu_mem": True,
    "show_gpu_fan": True,
    "show_tiles": True,
    "show_disk": True,
    "show_fan": True,
    "show_free": True,
    "show_procs": True,
    "show_footer": True,
}

def _truthy(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(value)

_running = True

def _stop(_signum, _frame):
    global _running
    _running = False

def _config_candidates(path: Optional[str]) -> List[str]:
    if path:
        return [path]
    return [
        "/etc/turmo-display/config.json",
        os.path.join(os.getcwd(), "config.json"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.example.json"),
    ]


def load_config_with_path(path: Optional[str] = None) -> Tuple[dict, Optional[str]]:
    """Load the configuration and remember which file was actually used."""

    config = dict(DEFAULT_CONFIG)
    used_path = None
    for candidate in _config_candidates(path):
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                config.update(data)
                used_path = candidate
                log.info("Config: %s", candidate)
                break
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Cannot read %s: %s", candidate, exc)
    return config, used_path


def load_config(path: Optional[str]) -> dict:
    return load_config_with_path(path)[0]


def config_write_path(path: Optional[str], used_path: Optional[str]) -> str:
    """Pick the file the web UI should write to.

    An explicitly requested path always wins.  Otherwise the file that was
    actually loaded is used, unless only ``config.example.json`` existed.
    """

    if path:
        return os.path.abspath(path)
    if used_path and os.path.basename(used_path) != "config.example.json":
        return os.path.abspath(used_path)
    return os.path.abspath(os.path.join(os.getcwd(), "config.json"))


def _config_mtime(path: Optional[str]) -> Optional[int]:
    if not path:
        return None
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def run(
    config: dict,
    config_path: Optional[str] = None,
    overrides: Optional[dict] = None,
) -> int:
    overrides = dict(overrides or {})
    current = dict(config)
    current.update(overrides)
    config_mtime = _config_mtime(config_path)

    refresh = max(0.2, float(current.get("refresh_seconds", 1.0)))
    orientation = int(current.get("orientation", 0))
    brightness = int(current.get("brightness", 85))

    sampler = Sampler()
    lcd = TuringRevA(
        port=str(current.get("port", "auto")),
        baud=int(current.get("baud", 115200)),
        orientation=orientation,
    )

    global _running
    _running = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    log.info("Looking for display…")
    while _running:
        try:
            lcd.open()
            lcd.hello()
            lcd.set_brightness(brightness)
            lcd.set_orientation(orientation)
            break
        except Exception as exc:
            lcd.close()
            log.warning("Display not ready yet: %s (retrying in 5 s)", exc)
            time.sleep(5)
    if not _running:
        return 0

    log.info(
        "Ready: %s, %dx%d, refresh %.1fs",
        lcd.model,
        lcd.get_width(),
        lcd.get_height(),
        refresh,
    )

    next_tick = time.monotonic()

    while _running:
        try:
            # The on-demand editor writes config.json; pick it up without a
            # service restart. CLI overrides still win.
            mtime = _config_mtime(config_path)
            if config_path and mtime is not None and mtime != config_mtime:
                loaded, _ = load_config_with_path(config_path)
                loaded.update(overrides)
                current = loaded
                config_mtime = mtime
                log.info("Config reloaded: %s", config_path)

            new_orientation = int(current.get("orientation", 0))
            if new_orientation != orientation:
                orientation = new_orientation
                lcd.set_orientation(orientation)

            new_brightness = int(current.get("brightness", 85))
            if new_brightness != brightness:
                brightness = new_brightness
                lcd.set_brightness(brightness)

            refresh = max(0.2, float(current.get("refresh_seconds", 1.0)))

            stats = sampler.sample()
            if not _truthy(current.get("show_gpu", True)):
                stats.gpu = None

            renderer = Renderer(
                lcd.get_width(),
                lcd.get_height(),
                current.get("hostname") or "",
                current,
            )
            frame = renderer.render(stats)

            # Always send the full frame for absolute stability and to avoid pixel drift
            lcd.display_image(frame, 0, 0)
            log.debug("Full frame sent")

        except Exception as exc:
            log.warning("Error: %s — trying to reconnect", exc)
            try:
                lcd.reconnect()
                lcd.set_orientation(orientation)
                lcd.set_brightness(brightness)
            except Exception as reconnect_error:
                log.error("Reconnect failed: %s", reconnect_error)
                time.sleep(5)
                continue

        next_tick += refresh
        delay = next_tick - time.monotonic()
        if delay < 0:
            next_tick = time.monotonic()
            delay = 0
        deadline = time.monotonic() + delay
        while _running and time.monotonic() < deadline:
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

    log.info("Stopped")
    lcd.close()
    return 0

def preview(config: dict, path: str, fake: bool = False) -> int:
    """Save the dashboard as a PNG (without a display)."""
    orientation = int(config.get("orientation", 0))
    width, height = (480, 320) if orientation in (1, 2, 3) else (320, 480)

    sampler = DemoSampler() if fake else Sampler()
    if not fake:
        # The first sample fills history/percentages; the second gives real rates.
        sampler.sample()
        time.sleep(0.3)
    stats = sampler.sample()
    if not _truthy(config.get("show_gpu", True)):
        stats.gpu = None

    image = Renderer(width, height, config.get("hostname") or "", config).render(stats)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    image.save(path)
    log.info("Preview saved: %s (%dx%d)", path, width, height)
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="turmo_display",
        description="BLACKBOX dashboard for TURMO / Turing Smart Screen on Linux",
    )
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--port", help="serial port (e.g. /dev/ttyUSB0 or auto)")
    parser.add_argument("--brightness", type=int, help="brightness 0-100")
    parser.add_argument("--orientation", type=int, choices=[0, 1, 2, 3], help="0=portrait, 2=landscape")
    parser.add_argument("--theme", help="theme (e.g. blackbox, nord, dracula, gruvbox)")
    parser.add_argument("--preview", metavar="PNG", help="save an image instead of sending it to the display")
    parser.add_argument("--fake", action="store_true", help="fake statistics (for previews)")
    parser.add_argument("--list-ports", action="store_true", help="list serial ports")
    parser.add_argument("--list-themes", action="store_true", help="list available themes")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser

def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_ports:
        print(list_ports_text())
        detected = find_port()
        print(f"\nAuto-detect: {detected or 'not found'}")
        return 0

    if args.list_themes:
        print("Available themes:\n")
        for name, label, description in theme_choices():
            print(f"  {name:<10} {label:<14} {description}")
        print("\nExample: --theme nord  or  \"theme\": \"nord\" in config.json")
        return 0

    config, used_path = load_config_with_path(args.config)

    overrides = {}
    if args.port:
        overrides["port"] = args.port
    if args.brightness is not None:
        overrides["brightness"] = args.brightness
    if args.orientation is not None:
        overrides["orientation"] = args.orientation
    if args.theme:
        overrides["theme"] = args.theme
    config.update(overrides)

    theme_id = str(config.get("theme", "blackbox")).strip().lower()
    if theme_id not in THEMES:
        log.warning("Unknown theme %r; using blackbox", theme_id)

    if args.preview:
        return preview(config, args.preview, args.fake)

    return run(config, config_write_path(args.config, used_path), overrides)

if __name__ == "__main__":
    sys.exit(main())
