"""Shared runtime state between the display loop and the web UI.

The display loop owns the serial port; the web server only changes the
configuration and reads the last rendered frame.  Everything is guarded by a
lock because the HTTP server runs in its own threads.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, Optional

from PIL import Image


class RuntimeConfig:
    """Thread-safe configuration, live frame and status for TURMO."""

    def __init__(self, config: Dict[str, Any], config_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._config = copy.deepcopy(dict(config))
        self.config_path = config_path
        self.revision = 0
        self._frame: Optional[Image.Image] = None
        self.frame_id = 0
        self.frame_time = 0.0
        self.started_at = time.time()
        self.last_activity = time.time()
        self.shutdown_requested_at: Optional[float] = None
        self.force_shutdown = False
        self._status: Dict[str, Any] = {
            "connected": False,
            "model": None,
            "width": None,
            "height": None,
            "port": None,
            "last_error": None,
        }

    # ------------------------------------------------------------ config
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._config)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._config.get(key, default))

    def update(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Merge validated changes and bump the revision."""

        with self._lock:
            self._config.update(copy.deepcopy(changes))
            self.revision += 1
            return copy.deepcopy(self._config)

    def save(self) -> Optional[str]:
        """Atomically write the configuration back to disk.

        Returns the written path, or ``None`` when no path is known.
        """

        with self._lock:
            if not self.config_path:
                return None
            path = os.path.abspath(self.config_path)
            directory = os.path.dirname(path) or "."
            os.makedirs(directory, exist_ok=True)
            data = json.dumps(self._config, indent=2, ensure_ascii=False) + "\n"
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=directory,
                prefix=".turmo-config-",
                suffix=".tmp",
                delete=False,
            )
            temporary = handle.name
            try:
                with handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            except Exception:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
            return path

    # ------------------------------------------------------------- frame
    def set_frame(self, image: Image.Image) -> None:
        with self._lock:
            self._frame = image.copy()
            self.frame_id += 1
            self.frame_time = time.time()

    def get_frame(self) -> Optional[Image.Image]:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    # ---------------------------------------------------------- activity
    def touch(self) -> None:
        with self._lock:
            self.last_activity = time.time()
        self.shutdown_requested_at: Optional[float] = None
        self.force_shutdown = False

    def idle_seconds(self) -> float:
        with self._lock:
            return time.time() - self.last_activity

    def request_shutdown(self, force: bool = False) -> None:
        with self._lock:
            self.shutdown_requested_at = time.time()
            self.force_shutdown = force

    def cancel_shutdown(self) -> None:
        with self._lock:
            self.shutdown_requested_at = None

    def shutdown_pending(self) -> bool:
        with self._lock:
            return self.shutdown_requested_at is not None

    def force_shutdown_requested(self) -> bool:
        with self._lock:
            return self.force_shutdown

    # ------------------------------------------------------------ status
    def set_status(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)

    def status_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            status = copy.deepcopy(self._status)
            status.update(
                {
                    "frame_id": self.frame_id,
                    "frame_age": (time.time() - self.frame_time) if self.frame_time else None,
                    "started_at": self.started_at,
                }
            )
            return status
