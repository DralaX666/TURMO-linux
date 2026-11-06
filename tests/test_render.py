"""Render smoke tests — no display and no real sensors required."""

from __future__ import annotations

import unittest

from PIL import Image

from turmo_display.render import Renderer
from turmo_display.stats import DemoSampler
from turmo_display.themes import THEMES, parse_color, resolve_theme


def _stats():
    return DemoSampler(history_len=30).sample()


class ThemeTests(unittest.TestCase):
    def test_all_themes_have_required_colors(self):
        for name, theme in THEMES.items():
            self.assertEqual(name, theme.name)
            self.assertTrue(theme.label)
            for field in (
                "bg_top",
                "bg_bottom",
                "card",
                "text",
                "muted",
                "dim",
                "accent",
                "amber",
                "blue",
                "green",
                "red",
                "plot_bg",
                "plot_grid",
            ):
                color = getattr(theme, field)
                self.assertEqual(len(color), 3, f"{name}.{field}")
                self.assertTrue(all(0 <= channel <= 255 for channel in color), f"{name}.{field}")

    def test_color_parsing(self):
        self.assertEqual(parse_color("#22e0be"), (34, 224, 190))
        self.assertEqual(parse_color("22e0be"), (34, 224, 190))
        self.assertEqual(parse_color("#2eb"), (34, 238, 187))
        self.assertEqual(parse_color([1, 2, 3]), (1, 2, 3))

    def test_theme_overrides(self):
        theme = resolve_theme("nord", {"accent": "#ff0000", "unknown": "ignored"})
        self.assertEqual(theme.name, "nord")
        self.assertEqual(theme.accent, (255, 0, 0))

    def test_unknown_theme_falls_back(self):
        self.assertEqual(resolve_theme("does-not-exist").name, "blackbox")


class RenderTests(unittest.TestCase):
    def test_every_theme_both_orientations(self):
        stats = _stats()
        for name in THEMES:
            for width, height in ((320, 480), (480, 320)):
                image = Renderer(width, height, options={"theme": name}).render(stats)
                self.assertIsInstance(image, Image.Image)
                self.assertEqual(image.size, (width, height))

    def test_all_panels_can_be_disabled(self):
        options = {
            "show_gpu": False,
            "show_system": False,
            "show_clock": False,
            "show_cpu": False,
            "show_memory": False,
            "show_network": False,
            "show_tiles": False,
            "show_footer": False,
        }
        image = Renderer(320, 480, options=options).render(_stats())
        self.assertEqual(image.size, (320, 480))

    def test_custom_title_and_footer(self):
        image = Renderer(
            320,
            480,
            options={
                "title": "MOJ SERVER",
                "subtitle": "// LAB",
                "footer_text": "CUSTOM",
            },
        ).render(_stats())
        self.assertEqual(image.size, (320, 480))

    def test_each_optional_detail_toggle(self):
        keys = (
            "show_cpu_temp",
            "show_cpu_freq",
            "show_cpu_load",
            "show_cpu_history",
            "show_swap",
            "show_net_totals",
            "show_net_history",
            "show_gpu_mem",
            "show_gpu_fan",
        )
        for key in keys:
            image = Renderer(320, 480, options={key: False}).render(_stats())
            self.assertEqual(image.size, (320, 480), key)


if __name__ == "__main__":
    unittest.main()
