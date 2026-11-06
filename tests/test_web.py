"""Tests for the web control panel (no display or serial port needed)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from PIL import Image

from turmo_display.app import DEFAULT_CONFIG
from turmo_display.runtime import RuntimeConfig
from turmo_display.webui.server import sanitize_changes, start_web_server


class SanitizeTests(unittest.TestCase):
    def test_web_editor_defaults(self):
        self.assertEqual(DEFAULT_CONFIG["web_port"], 8777)

    def test_accepts_valid_changes(self):
        changes, errors = sanitize_changes(
            {
                "theme": "nord",
                "show_cpu": False,
                "brightness": 120,
                "orientation": 2,
                "refresh_seconds": 0.1,
                "title": "  MOJ SERVER  ",
                "theme_colors": {"accent": "#ff8800"},
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(changes["theme"], "nord")
        self.assertFalse(changes["show_cpu"])
        self.assertEqual(changes["brightness"], 100)
        self.assertEqual(changes["orientation"], 2)
        self.assertEqual(changes["refresh_seconds"], 0.2)
        self.assertEqual(changes["title"], "MOJ SERVER")
        self.assertEqual(changes["theme_colors"], {"accent": "#ff8800"})

    def test_rejects_bad_values(self):
        changes, errors = sanitize_changes(
            {
                "theme": "nepostoji",
                "orientation": 9,
                "theme_colors": {"accent": "nije-boja", "unknown": "#ffffff"},
            }
        )
        self.assertEqual(changes, {})
        self.assertEqual(len(errors), 4)

    def test_ignores_unknown_keys(self):
        changes, errors = sanitize_changes({"port": "/dev/ttyUSB9", "nepoznato": 1})
        self.assertEqual(changes, {})
        self.assertEqual(errors, [])


class WebServerTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(dict(DEFAULT_CONFIG), handle)
        handle.close()
        self.config_path = handle.name
        self.runtime = RuntimeConfig(dict(DEFAULT_CONFIG), self.config_path)
        self.server = start_web_server(self.runtime, "127.0.0.1", 0)
        self.assertIsNotNone(self.server)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        try:
            os.unlink(self.config_path)
        except OSError:
            pass

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, response.headers.get("Content-Type"), response.read()

    def _post(self, payload):
        request = urllib.request.Request(
            self.base + "/api/config",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_state_and_assets(self):
        status, content_type, body = self._get("/api/state")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        state = json.loads(body)
        self.assertEqual(len(state["themes"]), 8)
        self.assertIn("config", state)
        self.assertIn("status", state)

        for path, expected in (("/", "text/html"), ("/app.js", "javascript"), ("/style.css", "text/css")):
            status, content_type, body = self._get(path)
            self.assertEqual(status, 200)
            self.assertIn(expected, content_type)
            self.assertGreater(len(body), 1000)

    def test_preview_images(self):
        status, content_type, body = self._get("/api/preview.png")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

        status, content_type, body = self._get("/api/theme-preview/dracula.png")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_locales_are_complete_and_served(self):
        keysets = {}
        for code in ("en", "de", "zh", "sr"):
            status, content_type, body = self._get(f"/locales/{code}.json")
            self.assertEqual(status, 200)
            self.assertIn("application/json", content_type)
            keysets[code] = set(json.loads(body))
        self.assertGreater(len(keysets["en"]), 100)
        for code, keys in keysets.items():
            self.assertEqual(keys, keysets["en"], code)

        status, content_type, body = self._get("/icon.png")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_preview_provider_is_used(self):
        runtime = RuntimeConfig(dict(DEFAULT_CONFIG), None)
        calls = []

        def provider():
            calls.append(1)
            return Image.new("RGB", (32, 48), (1, 2, 3))

        server = start_web_server(runtime, "127.0.0.1", 0, preview_provider=provider)
        self.assertIsNotNone(server)
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/api/preview.png", timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get("Content-Type"), "image/png")
            self.assertEqual(len(calls), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_shutdown_endpoint(self):
        runtime = RuntimeConfig(dict(DEFAULT_CONFIG), None)
        stopped = threading.Event()
        server = start_web_server(runtime, "127.0.0.1", 0, on_shutdown=stopped.set)
        self.assertIsNotNone(server)
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual(response.status, 200)
            self.assertTrue(stopped.wait(2))
        finally:
            server.shutdown()
            server.server_close()

    def test_non_loopback_host_is_forced_to_localhost(self):
        runtime = RuntimeConfig(dict(DEFAULT_CONFIG), None)
        server = start_web_server(runtime, "0.0.0.0", 0)
        self.assertIsNotNone(server)
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.shutdown()
            server.server_close()

    def test_unknown_locale_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self._get("/locales/xx.json")
        self.assertEqual(context.exception.code, 404)

    def test_config_update_is_persisted(self):
        status, state = self._post({"theme": "gruvbox", "show_net_history": False, "brightness": 55})
        self.assertEqual(status, 200)
        self.assertEqual(state["config"]["theme"], "gruvbox")
        self.assertFalse(state["config"]["show_net_history"])
        self.assertEqual(state["config"]["brightness"], 55)
        self.assertEqual(self.runtime.revision, 1)

        with open(self.config_path, encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["theme"], "gruvbox")
        self.assertFalse(saved["show_net_history"])
        self.assertEqual(saved["brightness"], 55)

    def test_invalid_update_returns_400(self):
        body = json.dumps({"theme": "nepostoji"}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/config",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
