"""Web control panel for the TURMO display.

The HTTP server is intentionally dependency-free (stdlib only) and runs in
background threads inside the display process.  It never touches the serial
port itself: it changes :class:`~turmo_display.runtime.RuntimeConfig`, and the
display loop picks the new settings up on its next tick.
"""

from __future__ import annotations

import io
import json
import logging
import os
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from PIL import Image

from ..render import Renderer
from ..runtime import RuntimeConfig
from ..stats import DemoSampler
from ..themes import COLOR_FIELDS, COLOR_FIELD_SET, THEMES, parse_color

log = logging.getLogger("turmo.web")

_ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/icon.png": ("icon.png", "image/png"),
}
LOCALES = ("en", "de", "zh", "sr")
_ASSET_CACHE: Dict[str, bytes] = {}
_ASSET_LOCK = threading.Lock()
_THEME_CACHE: Dict[str, bytes] = {}
_THEME_LOCK = threading.Lock()

BOOL_KEYS = (
    "show_gpu",
    "show_system",
    "show_clock",
    "show_cpu",
    "show_cpu_temp",
    "show_cpu_freq",
    "show_cpu_load",
    "show_cpu_history",
    "show_memory",
    "show_swap",
    "show_network",
    "show_net_totals",
    "show_net_history",
    "show_gpu_mem",
    "show_gpu_fan",
    "show_tiles",
    "show_disk",
    "show_fan",
    "show_free",
    "show_procs",
    "show_footer",
)
TEXT_KEYS = {"hostname": 64, "title": 48, "subtitle": 48, "footer_text": 48}

_TRUE = {"1", "true", "yes", "on", "da"}
_FALSE = {"0", "false", "no", "off", ""}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise ValueError("expected true or false")


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("expected an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError("expected an integer")


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("expected a number")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip().replace(",", "."))
    raise ValueError("expected a number")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _hex(color) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def sanitize_changes(payload: Any):
    """Validate a partial config update coming from the web UI.

    Returns ``(changes, errors)``.  Unknown keys are ignored so an older
    dashboard does not break when the UI knows about a newer option.
    """

    if not isinstance(payload, dict):
        return {}, ["Expected a JSON object."]

    changes: Dict[str, Any] = {}
    errors: List[str] = []

    for key, value in payload.items():
        if key in BOOL_KEYS:
            try:
                changes[key] = _as_bool(value)
            except ValueError:
                errors.append(f"{key}: {value!r} is not a boolean.")
        elif key == "brightness":
            try:
                changes[key] = int(_clamp(_as_int(value), 0, 100))
            except (TypeError, ValueError):
                errors.append("brightness must be a number between 0 and 100.")
        elif key == "orientation":
            try:
                orientation = _as_int(value)
                if orientation not in (0, 1, 2, 3):
                    raise ValueError
                changes[key] = orientation
            except (TypeError, ValueError):
                errors.append("orientation must be 0, 1, 2 or 3.")
        elif key == "refresh_seconds":
            try:
                changes[key] = round(_clamp(_as_float(value), 0.2, 60.0), 2)
            except (TypeError, ValueError):
                errors.append("refresh_seconds must be a number between 0.2 and 60.")
        elif key == "full_refresh_seconds":
            try:
                changes[key] = int(_clamp(_as_int(value), 1, 86400))
            except (TypeError, ValueError):
                errors.append("full_refresh_seconds must be an integer.")
        elif key in TEXT_KEYS:
            if not isinstance(value, str):
                errors.append(f"{key} must be text.")
                continue
            text = value.strip()
            if len(text) > TEXT_KEYS[key]:
                errors.append(f"{key} is too long (max {TEXT_KEYS[key]}).")
                continue
            changes[key] = text
        elif key == "theme":
            theme = str(value or "").strip().lower()
            if theme not in THEMES:
                errors.append(f"Unknown theme: {value!r}.")
            else:
                changes[key] = theme
        elif key == "theme_colors":
            if value in (None, {}):
                changes[key] = {}
                continue
            if not isinstance(value, dict):
                errors.append("theme_colors must be an object.")
                continue
            colors: Dict[str, str] = {}
            for raw_name, raw_value in value.items():
                name = str(raw_name).strip().lower()
                if name not in COLOR_FIELD_SET:
                    errors.append(f"Unknown color: {raw_name!r}.")
                    continue
                try:
                    colors[name] = _hex(parse_color(raw_value))
                except ValueError:
                    errors.append(f"Invalid color for {name}: {raw_value!r}.")
            changes[key] = colors
        # Other keys (port, baud, web_*) are deliberately not editable here.

    if errors:
        return {}, errors
    return changes, errors


def _theme_payload(theme) -> Dict[str, Any]:
    return {
        "id": theme.name,
        "label": theme.label,
        "description": theme.description,
        "colors": {field: _hex(getattr(theme, field)) for field in COLOR_FIELDS},
    }


def _state_payload(runtime: RuntimeConfig, host: str, port: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "revision": runtime.revision,
        "config": runtime.snapshot(),
        "config_path": runtime.config_path,
        "status": runtime.status_snapshot(),
        "themes": [_theme_payload(theme) for theme in THEMES.values()],
        "web": {"host": host, "port": port},
    }


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(value)


def _demo_image(config: Dict[str, Any]) -> Image.Image:
    try:
        orientation = int(config.get("orientation", 0))
    except (TypeError, ValueError):
        orientation = 0
    width, height = (480, 320) if orientation in (1, 2, 3) else (320, 480)
    sampler = DemoSampler(history_len=30)
    sampler.sample()
    stats = sampler.sample()
    if not _truthy(config.get("show_gpu", True)):
        stats.gpu = None
    return Renderer(width, height, config.get("hostname") or "", config).render(stats)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _theme_preview(theme_id: str) -> bytes:
    with _THEME_LOCK:
        cached = _THEME_CACHE.get(theme_id)
        if cached is not None:
            return cached
        sampler = DemoSampler(history_len=30)
        sampler.sample()
        image = Renderer(320, 480, "", {"theme": theme_id}).render(sampler.sample())
        data = _png_bytes(image)
        _THEME_CACHE[theme_id] = data
        return data


def _asset(name: str) -> bytes:
    with _ASSET_LOCK:
        cached = _ASSET_CACHE.get(name)
        if cached is not None:
            return cached
        with open(os.path.join(_ASSET_DIR, name), "rb") as handle:
            data = handle.read()
        _ASSET_CACHE[name] = data
        return data


class _Handler(BaseHTTPRequestHandler):
    server_version = "TURMO-Web/1.1"
    protocol_version = "HTTP/1.1"

    runtime: RuntimeConfig
    state_host: str
    state_port: int
    preview_provider = None
    on_shutdown = None
    on_client_change = None

    # ------------------------------------------------------------- helpers
    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib API
        log.debug("%s %s", self.address_string(), fmt % args)

    # ----------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        self.runtime.touch()
        self.runtime.cancel_shutdown()
        path = urlsplit(self.path).path
        if path == "/api/state":
            self._json(200, _state_payload(self.runtime, self.state_host, self.state_port))
            return

        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            if self.on_client_change is not None:
                self.on_client_change(True)
            try:
                while True:
                    try:
                        readable, _, _ = select.select([self.connection], [], [], 5)
                    except (OSError, ValueError):
                        break
                    if readable:
                        try:
                            data = self.connection.recv(4096, socket.MSG_PEEK)
                            if not data:
                                break
                            self.connection.recv(len(data))
                        except (BlockingIOError, InterruptedError):
                            pass
                        except OSError:
                            break
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                if self.on_client_change is not None:
                    self.on_client_change(False)
            return

        if path == "/api/preview.png":
            frame = None
            if self.preview_provider is not None:
                try:
                    frame = self.preview_provider()
                except Exception:
                    log.exception("Preview rendering failed")
            if frame is None:
                frame = self.runtime.get_frame()
            if frame is None:
                frame = _demo_image(self.runtime.snapshot())
            self._send(200, _png_bytes(frame), "image/png")
            return

        if path.startswith("/api/theme-preview/") and path.endswith(".png"):
            theme_id = unquote(path[len("/api/theme-preview/") : -len(".png")])
            if theme_id not in THEMES:
                self._error(404, "Unknown theme.")
                return
            self._send(200, _theme_preview(theme_id), "image/png", cache="public, max-age=3600")
            return

        if path.startswith("/locales/") and path.endswith(".json"):
            code = unquote(path[len("/locales/") : -len(".json")])
            if code not in LOCALES:
                self._error(404, "Unknown language.")
                return
            self._send(
                200,
                _asset(os.path.join("locales", f"{code}.json")),
                "application/json; charset=utf-8",
                cache="public, max-age=3600",
            )
            return

        asset = _ASSETS.get(path)
        if asset is not None:
            name, content_type = asset
            self._send(200, _asset(name), content_type)
            return

        self._error(404, "Not found.")

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib API
        self.do_GET()

    # ---------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        parts = urlsplit(self.path)
        path = parts.path
        if path == "/api/shutdown" and self.on_shutdown is not None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length:
                self.rfile.read(length)  # drain the beacon body
            force = parse_qs(parts.query).get("force", ["0"])[0] in ("1", "true", "yes")
            self.runtime.request_shutdown(force=force)
            self._json(200, {"ok": True, "force": force})
            threading.Thread(target=self.on_shutdown, name="turmo-web-stop", daemon=True).start()
            return
        self.runtime.touch()
        self.runtime.cancel_shutdown()
        if path != "/api/config":
            self._error(404, "Not found.")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._error(400, "Invalid Content-Length.")
            return
        if length > 64 * 1024:
            self._error(413, "Request too large.")
            return

        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "Invalid JSON.")
            return

        changes, errors = sanitize_changes(payload)
        if errors:
            self._json(400, {"ok": False, "errors": errors})
            return

        if changes:
            self.runtime.update(changes)
            try:
                self.runtime.save()
            except OSError as exc:
                log.warning("Could not save config: %s", exc)
                self._json(
                    500,
                    {
                        "ok": False,
                        "error": f"Changes were applied, but saving failed: {exc}",
                        "state": _state_payload(self.runtime, self.state_host, self.state_port),
                    },
                )
                return
            log.info("Web GUI: changed %s", ", ".join(sorted(changes)))

        self._json(200, _state_payload(self.runtime, self.state_host, self.state_port))


def _handler_for(
    runtime: RuntimeConfig,
    host: str,
    port: int,
    preview_provider=None,
    on_shutdown=None,
    on_client_change=None,
):
    class Handler(_Handler):
        pass

    Handler.runtime = runtime
    Handler.state_host = host
    Handler.state_port = port
    Handler.preview_provider = staticmethod(preview_provider) if preview_provider else None
    Handler.on_shutdown = staticmethod(on_shutdown) if on_shutdown else None
    Handler.on_client_change = staticmethod(on_client_change) if on_client_change else None
    return Handler


class _ThreadingServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _advertised_urls(host: str, port: int) -> List[str]:
    return [f"http://{host}:{port}"]


def start_web_server(
    runtime: RuntimeConfig,
    host: str = "127.0.0.1",
    port: int = 8777,
    preview_provider=None,
    on_shutdown=None,
    on_client_change=None,
) -> Optional[ThreadingHTTPServer]:
    """Start the control panel in a background thread.

    Returns the server (useful for tests and shutdown) or ``None`` when the
    address is already in use or cannot be bound.
    """

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 8777

    # The control panel is an editor for the machine physically connected to
    # the display. It must never be reachable from the network.
    if host not in ("127.0.0.1", "::1"):
        log.warning("Web GUI is local-only; ignoring host %r and binding to 127.0.0.1", host)
        host = "127.0.0.1"

    try:
        server = _ThreadingServer(
            (host, port),
            _handler_for(
                runtime,
                host,
                port,
                preview_provider,
                on_shutdown,
                on_client_change,
            ),
        )
    except OSError as exc:
        log.warning("Web GUI could not start on %s:%s: %s", host, port, exc)
        return None

    thread = threading.Thread(target=server.serve_forever, name="turmo-web", daemon=True)
    thread.start()

    actual_port = server.server_address[1]
    log.info("Web GUI: %s", "  ·  ".join(_advertised_urls(host, actual_port)))
    return server
