"""BLACKBOX dashboard renderer (Pillow).

Crta se u baznoj rezoluciji 320x480 (portrait) ili 480x320 (landscape), a zatim
se skalira na stvarnu rezoluciju displeja.

Izgled se kontroliše kroz ``options`` (config.json):
    theme, theme_colors, title, subtitle, footer_text,
    show_clock, show_cpu, show_gpu, show_system, show_memory, show_network,
    show_tiles, show_disk, show_fan, show_free, show_procs, show_footer,
    show_cpu_temp, show_cpu_freq, show_cpu_load, show_cpu_history,
    show_swap, show_net_totals, show_net_history, show_gpu_mem, show_gpu_fan.

Palete su u :mod:`turmo_display.themes`; renderer ne sadrži hardkodovane boje.
"""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .stats import Stats
from .themes import Theme, resolve_theme

_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/ubuntu",
    "C:\\Windows\\Fonts",
]

_CANDIDATES = {
    "mono": ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "UbuntuMono-R.ttf", "consola.ttf"],
    "mono_bold": ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf", "UbuntuMono-B.ttf", "consolab.ttf"],
    "sans": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Ubuntu-R.ttf", "segoeui.ttf"],
    "sans_bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Ubuntu-B.ttf", "segoeuib.ttf"],
}


@lru_cache(maxsize=128)
def _font(kind: str, size: int):
    for directory in _FONT_DIRS:
        for name in _CANDIDATES[kind]:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _mix(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _ellipsis(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "\u2026"
    while text and draw.textlength(text + suffix, font=font) > max_width:
        text = text[:-1]
    return text + suffix


def _human_bytes(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "\u2014"
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{value:.0f} B{suffix}"
            return f"{value:.1f} {unit}{suffix}"
        value /= 1024.0
    return "\u2014"


def _rate(value: float) -> str:
    if value < 1024:
        return f"{value:.0f} B/s"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB/s"
    return f"{value / (1024 * 1024):.1f} MB/s"


def _short_bytes(value: Optional[float]) -> str:
    if value is None:
        return "\u2014"
    value = float(value)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(value) < 1024.0 or unit == "T":
            if unit == "B" or value >= 100:
                return f"{value:.0f}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return "\u2014"


def _uptime(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    return f"{hours:02d}h {minutes:02d}m"


_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _date_text(now: datetime) -> str:
    return f"{_DAYS[now.weekday()]} {now.day:02d} {_MONTHS[now.month - 1]}"


class Renderer:
    def __init__(
        self,
        width: int = 320,
        height: int = 480,
        base_hostname: str = "",
        options: Optional[Dict] = None,
    ):
        self.width = width
        self.height = height
        self.base_hostname = base_hostname
        self.options = dict(options or {})
        self.theme: Theme = resolve_theme(
            self.options.get("theme", "blackbox"),
            self.options.get("theme_colors"),
        )
        self.title = str(self.options.get("title") or "BLACKBOX")
        self.footer_text = str(self.options.get("footer_text") or "TURMO / LINUX")

    # ---------------------------------------------------------- opcije
    def _opt(self, key: str, default: bool = True) -> bool:
        value = self.options.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off", "")
        return bool(value)

    def _text(self, key: str, default: str) -> str:
        value = self.options.get(key)
        return str(value) if value not in (None, "") else default

    def render(self, stats: Stats) -> Image.Image:
        if self.width >= self.height:
            base = self._landscape(stats)
        else:
            base = self._portrait(stats)

        if base.size == (self.width, self.height):
            return base

        return base.resize((self.width, self.height), Image.LANCZOS)

    # ------------------------------------------------------------- osnova
    def _background(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        theme = self.theme
        for y in range(height):
            draw.line(
                (0, y, width, y),
                fill=_mix(theme.bg_top, theme.bg_bottom, y / max(1, height - 1)),
            )
        for x in range(0, width, 32):
            draw.line((x, 0, x, height), fill=theme.grid)
        for y in range(0, height, 32):
            draw.line((0, y, width, y), fill=theme.grid)

    def _separator(self, draw, x1, y, x2):
        draw.line((x1, y, x2, y), fill=self.theme.border)
        draw.line((x1, y, min(x1 + 26, x2), y), fill=self.theme.accent)

    @staticmethod
    def _tracked(draw, x, y, text: str, font, fill, tracking: int = 1) -> None:
        for char in text:
            draw.text((x, y), char, font=font, fill=fill)
            x += draw.textlength(char, font=font) + tracking

    def _card(self, draw, box, title: str, accent=None, right: str = "") -> None:
        theme = self.theme
        if accent is None:
            accent = theme.accent
        x1, y1, x2, y2 = box
        draw.rounded_rectangle((x1, y1 + 2, x2, y2 + 2), radius=8, fill=theme.card_shadow)
        draw.rounded_rectangle(box, radius=8, fill=theme.card, outline=theme.border, width=1)
        draw.line((x1 + 12, y1 + 1, x2 - 12, y1 + 1), fill=theme.highlight)
        draw.rounded_rectangle((x1 + 4, y1 + 8, x1 + 7, y1 + 20), radius=1, fill=accent)
        self._tracked(draw, x1 + 11, y1 + 7, title, _font("mono", 8), theme.muted)
        if right:
            draw.text(
                (x2 - 10, y1 + 8),
                right,
                font=_font("mono", 7),
                fill=theme.dim,
                anchor="ra",
            )

    def _sparkline(self, draw, box, values: Iterable[float], color, maximum: float = 100.0) -> None:
        x1, y1, x2, y2 = box
        if y2 - y1 < 6 or x2 - x1 < 6:
            return
        theme = self.theme
        draw.rounded_rectangle(box, radius=4, fill=theme.plot_bg, outline=theme.border)
        for fraction in (0.33, 0.66):
            gy = int(y2 - (y2 - y1) * fraction)
            draw.line((x1 + 2, gy, x2 - 2, gy), fill=theme.plot_grid)
        values = [max(0.0, min(maximum, float(v))) for v in values]
        if len(values) < 2:
            return
        width = max(1, x2 - x1 - 4)
        height = max(1, y2 - y1 - 4)
        step = width / (len(values) - 1)
        points = [
            (x1 + 2 + index * step, y2 - 2 - (value / maximum) * height)
            for index, value in enumerate(values)
        ]
        shade = _mix(theme.plot_bg, color, 0.16)
        draw.polygon(points + [(x2 - 2, y2 - 2), (x1 + 2, y2 - 2)], fill=shade)
        glow = _mix(theme.plot_bg, color, 0.45)
        draw.line(points, fill=glow, width=3, joint="curve")
        draw.line(points, fill=color, width=1, joint="curve")
        ex, ey = points[-1]
        draw.ellipse((ex - 2, ey - 2, ex + 2, ey + 2), fill=color)
        draw.ellipse((ex - 1, ey - 1, ex + 1, ey + 1), fill=_mix(color, theme.text, 0.55))

    def _sparkline_multi(self, draw, box, series, colors, maximum: Optional[float] = None) -> None:
        x1, y1, x2, y2 = box
        if y2 - y1 < 8 or x2 - x1 < 8:
            return
        theme = self.theme
        draw.rounded_rectangle(box, radius=4, fill=theme.plot_bg, outline=theme.border)
        for fraction in (0.33, 0.66):
            gy = int(y2 - (y2 - y1) * fraction)
            draw.line((x1 + 2, gy, x2 - 2, gy), fill=theme.plot_grid)
        usable = [[max(0.0, float(v)) for v in values] for values in series]
        if maximum is None:
            maximum = max([1.0] + [v for values in usable for v in values])
        width = max(1, x2 - x1 - 4)
        height = max(1, y2 - y1 - 4)
        for values, color in zip(usable, colors):
            if len(values) < 2:
                continue
            step = width / (len(values) - 1)
            points = [
                (x1 + 2 + index * step, y2 - 2 - (min(maximum, value) / maximum) * height)
                for index, value in enumerate(values)
            ]
            shade = _mix(theme.plot_bg, color, 0.10)
            draw.polygon(points + [(x2 - 2, y2 - 2), (x1 + 2, y2 - 2)], fill=shade)
            draw.line(points, fill=_mix(theme.plot_bg, color, 0.45), width=2, joint="curve")
            draw.line(points, fill=color, width=1, joint="curve")
            ex, ey = points[-1]
            draw.ellipse((ex - 1, ey - 1, ex + 1, ey + 1), fill=color)

    def _big_value(self, draw, x, y, value: str, unit: str = "", color=None, size=32) -> int:
        theme = self.theme
        if color is None:
            color = theme.text
        draw.text((x, y), value, font=_font("mono_bold", size), fill=color)
        if unit:
            width = draw.textlength(value, font=_font("mono_bold", size))
            draw.text(
                (x + width + 3, y + int(size * 0.44)),
                unit,
                font=_font("mono", max(8, size // 3)),
                fill=theme.muted,
            )
            return int(width) + 18
        return int(draw.textlength(value, font=_font("mono_bold", size)))

    def _bar(self, draw, box, pct: Optional[float], color) -> None:
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, radius=max(1, (y2 - y1) // 2), fill=self.theme.track)
        if pct is None:
            return
        pct = max(0.0, min(100.0, float(pct)))
        fill_width = int((x2 - x1) * pct / 100.0)
        if fill_width > 1:
            draw.rounded_rectangle(
                (x1, y1, x1 + fill_width, y2), radius=max(1, (y2 - y1) // 2), fill=color
            )

    @staticmethod
    def _dot(draw, x, y, color, radius=2):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def _tile(self, draw, box, title, value, unit="", sub="", color=None, accent=None, compact=False) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, radius=7, fill=theme.card, outline=theme.border, width=1)
        if accent:
            draw.line((x1 + 8, y1 + 1, x2 - 8, y1 + 1), fill=accent)
        label_size = 6 if compact else 7
        value_size = 13 if compact else 15
        draw.text((x1 + 7, y1 + 6), title, font=_font("mono", label_size), fill=theme.dim)
        if unit:
            draw.text((x2 - 7, y1 + 6), unit, font=_font("mono", 6), fill=theme.muted, anchor="ra")
        draw.text(
            (x1 + 7, y1 + (14 if compact else 15)),
            value,
            font=_font("mono_bold", value_size),
            fill=color or theme.text,
        )
        if sub:
            draw.text(
                (x1 + 7, y2 - 9),
                _ellipsis(draw, sub, _font("mono", label_size), x2 - x1 - 14),
                font=_font("mono", label_size),
                fill=theme.dim,
            )

    # ------------------------------------------------------- zaglavlje
    def _header(self, draw, x1: int, right: int, stats: Stats, subtitle: str) -> None:
        theme = self.theme
        subtitle = self._text("subtitle", subtitle)
        draw.rounded_rectangle((x1, 10, x1 + 5, 23), radius=1, fill=theme.accent)
        draw.text((x1 + 12, 9), self.title, font=_font("mono_bold", 11), fill=theme.text)
        title_width = int(draw.textlength(self.title, font=_font("mono_bold", 11)))
        draw.text((x1 + 12 + title_width + 8, 11), subtitle, font=_font("mono", 7), fill=theme.dim)

        hostname = self.base_hostname or stats.hostname
        ip_display = stats.net_ip if stats.net_ip and stats.net_ip != "-" else hostname
        truncated = _ellipsis(draw, ip_display, _font("mono", 8), right - x1 - 120)
        width = draw.textlength(truncated, font=_font("mono", 8))
        self._dot(draw, right - width - 8, 17, theme.green, 2)
        draw.text((right, 12), truncated, font=_font("mono", 8), fill=theme.green, anchor="ra")

        self._separator(draw, x1, 29, right)

    def _clock(self, draw, x1: int, right: int, stats: Stats, time_size: int) -> None:
        theme = self.theme
        now = stats.now
        draw.text((x1, 30), now.strftime("%H:%M"), font=_font("mono_bold", time_size), fill=theme.text)
        time_width = draw.textlength(now.strftime("%H:%M"), font=_font("mono_bold", time_size))
        draw.text(
            (x1 + time_width + 4, 31 + int(time_size * 0.54)),
            now.strftime("%S"),
            font=_font("mono_bold", 12),
            fill=theme.accent,
        )
        draw.text((right, 33), _date_text(now), font=_font("mono", 10), fill=theme.text, anchor="ra")
        draw.text((right, 48), f"UP {_uptime(stats.uptime_s)}", font=_font("mono", 8), fill=theme.muted, anchor="ra")
        draw.text(
            (right, 62),
            _ellipsis(draw, stats.distro, _font("mono", 7), 160),
            font=_font("mono", 7),
            fill=theme.dim,
            anchor="ra",
        )

    # ---------------------------------------------------------- raspored
    def _stack(self, x1, x2, top, bottom, specs, gap=6, max_scale=2.4):
        """Složi kartice po visini; višak prostora se raspodeli bez rupa."""
        if not specs or bottom <= top:
            return []
        heights = [float(h) for _, h in specs]
        count = len(specs)
        available = bottom - top
        natural = max(1.0, sum(heights))
        total = natural + gap * (count - 1)
        scale = 1.0
        if abs(total - available) > 0.5:
            target = (available - gap * (count - 1)) / natural
            scale = max(0.45, min(max_scale, target))
        heights = [max(18, int(round(h * scale))) for h in heights]
        total = sum(heights) + gap * (count - 1)
        y = top + max(0, (available - total) // 2)
        boxes = []
        for index, (key, _natural) in enumerate(specs):
            boxes.append((key, (x1, y, x2, y + heights[index])))
            y += heights[index] + gap
        return boxes

    # ------------------------------------------------------------ kartice
    def _draw_cpu(self, draw, box, stats: Stats, size: int = 42) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        self._card(draw, box, "CPU", theme.accent, f"{stats.cpu_cores} CORES")
        self._big_value(draw, x1 + 10, y1 + 18, f"{stats.cpu_pct:.0f}", "%", theme.text, size)

        if self._opt("show_cpu_temp", True):
            draw.text((x2 - 10, y1 + 20), "TEMP", font=_font("mono", 6), fill=theme.dim, anchor="ra")
            if stats.cpu_temp is not None:
                temp_color = theme.red if stats.cpu_temp > 75 else theme.amber
                draw.text(
                    (x2 - 10, y1 + 28),
                    f"{stats.cpu_temp:.0f}\u00b0C",
                    font=_font("mono_bold", 20 if size >= 40 else 18),
                    fill=temp_color,
                    anchor="ra",
                )
        if self._opt("show_cpu_freq", True) and stats.cpu_freq_ghz is not None:
            draw.text(
                (x2 - 10, y1 + 49),
                f"{stats.cpu_freq_ghz:.2f} GHz",
                font=_font("mono", 8),
                fill=theme.muted,
                anchor="ra",
            )

        show_load = self._opt("show_cpu_load", True)
        spark_top = y1 + 60
        spark_bottom = y2 - (18 if show_load else 10)
        if spark_bottom > spark_top + 8:
            if self._opt("show_cpu_history", True):
                self._sparkline(
                    draw,
                    (x1 + 10, spark_top, x2 - 10, spark_bottom),
                    stats.cpu_history,
                    theme.accent,
                )
            else:
                self._bar(
                    draw,
                    (x1 + 10, spark_bottom - 7, x2 - 10, spark_bottom),
                    stats.cpu_pct,
                    theme.accent,
                )

        if show_load:
            load = stats.load
            draw.text(
                (x1 + 10, y2 - 9),
                f"load {load[0]:.2f}  {load[1]:.2f}  {load[2]:.2f}",
                font=_font("mono", 7),
                fill=theme.dim,
            )

    def _draw_gpu(self, draw, box, stats: Stats, landscape: bool = False) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        gpu = stats.gpu
        if gpu is None:
            return
        self._card(draw, box, "GPU", theme.blue, _ellipsis(draw, gpu.name, _font("mono", 7), 168))
        self._big_value(
            draw,
            x1 + 10,
            y1 + 17,
            f"{gpu.pct:.0f}" if gpu.pct is not None else "\u2014",
            "%",
            theme.text,
            28,
        )
        if gpu.temp is not None:
            draw.text(
                (x2 - 10, y1 + 18),
                f"{gpu.temp:.0f}\u00b0C",
                font=_font("mono_bold", 15),
                fill=theme.amber,
                anchor="ra",
            )
        if self._opt("show_gpu_mem", True) and gpu.mem_total:
            draw.text(
                (x1 + 10, y1 + 45),
                f"{_human_bytes(gpu.mem_used)} / {_human_bytes(gpu.mem_total)}",
                font=_font("mono", 8),
                fill=theme.muted,
            )
        if self._opt("show_gpu_fan", True) and gpu.fan is not None:
            draw.text((x2 - 10, y1 + 45), f"fan {gpu.fan:.0f}%", font=_font("mono", 8), fill=theme.dim, anchor="ra")

        if landscape:
            self._bar(draw, (x1 + 10, y2 - 52, x2 - 10, y2 - 45), gpu.pct, theme.blue)
            draw.text(
                (x1 + 10, y2 - 33),
                _ellipsis(draw, stats.distro, _font("mono", 7), x2 - x1 - 20),
                font=_font("mono", 7),
                fill=theme.dim,
            )
            draw.text(
                (x1 + 10, y2 - 19),
                _ellipsis(draw, f"kernel {stats.kernel}", _font("mono", 7), x2 - x1 - 20),
                font=_font("mono", 7),
                fill=theme.dim,
            )
        else:
            self._bar(draw, (x1 + 10, y2 - 20, x2 - 10, y2 - 13), gpu.pct, theme.blue)

    def _draw_system(self, draw, box, stats: Stats, landscape: bool = False) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        self._card(draw, box, "SYSTEM", theme.blue)

        rows = [
            (_ellipsis(draw, stats.distro, _font("mono", 9), x2 - x1 - 20), theme.text, 9),
            (_ellipsis(draw, stats.kernel, _font("mono", 8), x2 - x1 - 20), theme.muted, 8),
            (f"uptime {_uptime(stats.uptime_s)}", theme.muted, 8),
            (f"procs {stats.procs}", theme.muted, 8),
        ]
        top = y1 + 15
        bottom = y2 - 14
        spacing = min(16, max(12, (bottom - top) // max(1, len(rows))))
        start = top + max(0, (bottom - top - spacing * (len(rows) - 1)) // 2)
        for index, (text, color, size) in enumerate(rows):
            draw.text((x1 + 10, start + index * spacing), text, font=_font("mono", size), fill=color)

        last_y = start + len(rows) * spacing
        if stats.nvme_temp is not None:
            nvme_color = theme.red if stats.nvme_temp > 65 else theme.amber
            draw.text((x1 + 10, last_y), f"nvme {stats.nvme_temp:.0f}\u00b0C", font=_font("mono", 8), fill=nvme_color)
        if stats.fan_rpm:
            draw.text(
                (x2 - 10, last_y),
                f"fan {stats.fan_rpm:.0f} rpm",
                font=_font("mono", 8),
                fill=theme.dim,
                anchor="ra",
            )

    def _draw_memory(self, draw, box, stats: Stats) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        mem_pct = (stats.mem_used / stats.mem_total * 100) if stats.mem_total else 0
        mem_free = max(0, stats.mem_total - stats.mem_used)
        self._card(draw, box, "MEMORY", theme.amber, f"{mem_pct:.0f}% USED")

        used_text = _human_bytes(stats.mem_used)
        draw.text((x1 + 10, y1 + 18), used_text, font=_font("mono_bold", 18), fill=theme.text)
        used_width = draw.textlength(used_text, font=_font("mono_bold", 18))
        draw.text(
            (x1 + 10 + used_width, y1 + 24),
            f" / {_human_bytes(stats.mem_total)}",
            font=_font("mono", 10),
            fill=theme.muted,
        )
        draw.text((x1 + 10, y2 - 24), f"free {_human_bytes(mem_free)}", font=_font("mono", 7), fill=theme.dim)
        if self._opt("show_swap", True) and stats.swap_total:
            draw.text(
                (x2 - 10, y2 - 24),
                f"swap {_human_bytes(stats.swap_used)}",
                font=_font("mono", 7),
                fill=theme.dim,
                anchor="ra",
            )
        spark_top = y1 + 44
        spark_bottom = y2 - 30
        if spark_bottom > spark_top + 8 and len(stats.mem_history) > 1:
            self._sparkline(draw, (x1 + 10, spark_top, x2 - 10, spark_bottom), stats.mem_history, theme.amber)
        self._bar(draw, (x1 + 10, y2 - 13, x2 - 10, y2 - 6), mem_pct, theme.amber)

    def _draw_net(self, draw, box, stats: Stats) -> None:
        theme = self.theme
        x1, y1, x2, y2 = box
        self._card(
            draw,
            box,
            "NET",
            theme.green,
            _ellipsis(draw, f"{stats.net_iface} \u00b7 {stats.net_ip}", _font("mono", 7), 158),
        )
        down_y = max(y1 + 18, (y1 + y2) // 2 - 19)
        up_y = down_y + 20
        show_history = self._opt("show_net_history", True)
        history = show_history and (len(stats.net_rx_history) > 1 or len(stats.net_tx_history) > 1)
        if y2 - y1 >= 100 and history:
            down_y = y1 + 18
            up_y = y1 + 38
        else:
            up_y = down_y + min(22, max(18, (y2 - y1) - 42))
        draw.text((x1 + 10, down_y), f"\u2193 {_rate(stats.net_rx)}", font=_font("mono_bold", 14), fill=theme.green)
        draw.text((x1 + 10, up_y), f"\u2191 {_rate(stats.net_tx)}", font=_font("mono_bold", 11), fill=theme.blue)
        if self._opt("show_net_totals", True) and stats.net_rx_total:
            draw.text(
                (x2 - 10, down_y + 3),
                f"\u03a3 {_short_bytes(stats.net_rx_total)}",
                font=_font("mono", 7),
                fill=theme.dim,
                anchor="ra",
            )
            draw.text(
                (x2 - 10, up_y + 2),
                f"\u03a3 {_short_bytes(stats.net_tx_total)}",
                font=_font("mono", 7),
                fill=theme.dim,
                anchor="ra",
            )
        if y2 - y1 >= 100 and history:
            self._sparkline_multi(
                draw,
                (x1 + 10, y1 + 58, x2 - 10, y2 - 12),
                (stats.net_rx_history, stats.net_tx_history),
                (theme.green, theme.blue),
            )

    # ------------------------------------------------------------- tile
    def _tile_specs(self, stats: Stats):
        theme = self.theme
        specs = []
        disks = stats.disks
        disk_free = stats.disk_free or max(0, stats.disk_total - stats.disk_used)
        combined_pct = (stats.disk_used / stats.disk_total * 100) if stats.disk_total else 0

        if self._opt("show_disk", True):
            if len(disks) == 2:
                for disk in disks:
                    pct = (disk.used / disk.total * 100) if disk.total else 0
                    specs.append(
                        (
                            disk.label,
                            f"{pct:.0f}%",
                            "",
                            f"{_short_bytes(disk.free)} free",
                            theme.amber,
                            theme.amber,
                        )
                    )
            elif disks:
                sub = (
                    f"{len(disks)} disks"
                    if len(disks) > 2
                    else f"{_short_bytes(stats.disk_used)}/{_short_bytes(stats.disk_total)}"
                )
                specs.append(("DISK", f"{combined_pct:.0f}%", "", sub, theme.amber, theme.amber))

        if self._opt("show_free", True):
            free_sub = f"{len(disks)} disks" if len(disks) > 1 else "on disk"
            specs.append(("FREE", _short_bytes(disk_free), "", free_sub, theme.green, theme.green))

        if self._opt("show_fan", True):
            specs.append(
                (
                    "FAN",
                    f"{stats.fan_rpm:.0f}" if stats.fan_rpm else "\u2014",
                    "RPM" if stats.fan_rpm else "",
                    f"nvme {stats.nvme_temp:.0f}\u00b0C" if stats.nvme_temp else "",
                    theme.text,
                    theme.blue,
                )
            )

        if self._opt("show_procs", True):
            specs.append(("PROC", f"{stats.procs}", "", "running", theme.blue, theme.accent))
        return specs

    def _draw_tiles(self, draw, box, specs, rows: int, cols: int) -> None:
        if not specs or rows <= 0 or cols <= 0:
            return
        x1, y1, x2, y2 = box
        gap = 6 if len(specs) >= 5 else 8
        tile_w = (x2 - x1 - gap * (cols - 1)) // cols
        tile_h = (y2 - y1 - gap * (rows - 1)) // rows
        compact = tile_w < 60
        for index, (title, value, unit, sub, color, accent) in enumerate(specs):
            row, col = divmod(index, cols)
            in_row = min(cols, len(specs) - row * cols)
            offset = (cols - in_row) * (tile_w + gap) // 2
            tx = x1 + offset + col * (tile_w + gap)
            ty = y1 + row * (tile_h + gap)
            self._tile(
                draw,
                (tx, ty, tx + tile_w, ty + tile_h),
                title,
                value,
                unit,
                sub,
                color,
                accent,
                compact=compact,
            )

    # ------------------------------------------------------------- footer
    def _footer(self, draw, x1: int, right: int, stats: Stats, y: int, compact: bool = False) -> None:
        theme = self.theme
        size = 6 if compact else 7
        draw.text(
            (x1, y),
            _ellipsis(draw, f"{stats.hostname} \u00b7 {stats.kernel}", _font("mono", size), right - x1 - 90),
            font=_font("mono", size),
            fill=theme.dim,
        )
        draw.text((right, y), self.footer_text, font=_font("mono", 6), fill=theme.dim, anchor="ra")

    # ------------------------------------------------------------- portrait
    def _portrait(self, stats: Stats) -> Image.Image:
        image = Image.new("RGB", (320, 480), self.theme.bg_top)
        draw = ImageDraw.Draw(image)
        self._background(draw, 320, 480)

        margin = 12
        right = 308
        show_footer = self._opt("show_footer", True)

        self._header(draw, margin, right, stats, "// SYS MONITOR")
        cards_top = 88
        if self._opt("show_clock", True):
            self._clock(draw, margin, right, stats, 40)
        else:
            cards_top = 38

        tiles = self._tile_specs(stats) if self._opt("show_tiles", True) else []
        content_bottom = 458 if show_footer else 472
        tiles_box = None
        if tiles:
            tiles_box = (margin, content_bottom - 42, right, content_bottom)
            cards_bottom = tiles_box[1] - 6
        else:
            cards_bottom = content_bottom

        specs = []
        if self._opt("show_cpu", True):
            specs.append(("cpu", 100))
        gpu_visible = self._opt("show_gpu", True) and stats.gpu is not None
        system_visible = self._opt("show_system", True) and (stats.gpu is None or not self._opt("show_gpu", True))
        if gpu_visible or system_visible:
            specs.append(("gpu", 82))
        if self._opt("show_memory", True):
            specs.append(("memory", 62))
        if self._opt("show_network", True):
            specs.append(("net", 58))

        for key, box in self._stack(margin, right, cards_top, cards_bottom, specs):
            if key == "cpu":
                self._draw_cpu(draw, box, stats, 42)
            elif key == "gpu":
                if gpu_visible:
                    self._draw_gpu(draw, box, stats)
                else:
                    self._draw_system(draw, box, stats)
            elif key == "memory":
                self._draw_memory(draw, box, stats)
            elif key == "net":
                self._draw_net(draw, box, stats)

        if tiles_box is not None:
            self._draw_tiles(draw, tiles_box, tiles, 1, len(tiles))

        if show_footer:
            self._footer(draw, margin, right, stats, 464)
        return image

    # ------------------------------------------------------------ landscape
    def _landscape(self, stats: Stats) -> Image.Image:
        image = Image.new("RGB", (480, 320), self.theme.bg_top)
        draw = ImageDraw.Draw(image)
        self._background(draw, 480, 320)

        left_x = 12
        left_r = 226
        right_x = 238
        right_r = 468
        show_footer = self._opt("show_footer", True)

        self._header(draw, left_x, left_r, stats, "// SYS")
        cards_top = 80
        if self._opt("show_clock", True):
            self._clock(draw, left_x, left_r, stats, 36)
        else:
            cards_top = 36

        content_bottom = 298 if show_footer else 312

        # leva kolona: CPU + GPU/SYSTEM
        left_specs = []
        if self._opt("show_cpu", True):
            left_specs.append(("cpu", 98))
        gpu_visible = self._opt("show_gpu", True) and stats.gpu is not None
        system_visible = self._opt("show_system", True) and (stats.gpu is None or not self._opt("show_gpu", True))
        if gpu_visible or system_visible:
            left_specs.append(("gpu", 114))

        for key, box in self._stack(left_x, left_r, cards_top, content_bottom, left_specs, gap=8):
            if key == "cpu":
                self._draw_cpu(draw, box, stats, 36)
            elif key == "gpu":
                if gpu_visible:
                    self._draw_gpu(draw, box, stats, landscape=True)
                else:
                    self._draw_system(draw, box, stats, landscape=True)

        # desna kolona: MEMORY + NET + tile-ovi
        tiles = self._tile_specs(stats) if self._opt("show_tiles", True) else []
        tile_rows = 2 if len(tiles) >= 4 else 1
        tile_cols = (3 if len(tiles) >= 5 else 2) if tile_rows == 2 else max(1, len(tiles))
        right_specs = []
        if self._opt("show_memory", True):
            right_specs.append(("memory", 74))
        if self._opt("show_network", True):
            right_specs.append(("net", 76))
        if tiles:
            right_specs.append(("tiles", 120 if tile_rows == 2 else 56))

        tile_box = None
        for key, box in self._stack(right_x, right_r, 10, content_bottom, right_specs, gap=8):
            if key == "memory":
                self._draw_memory(draw, box, stats)
            elif key == "net":
                self._draw_net(draw, box, stats)
            elif key == "tiles":
                tile_box = box

        if tile_box is not None:
            self._draw_tiles(draw, tile_box, tiles, tile_rows, tile_cols)

        if show_footer:
            self._footer(draw, left_x, right_r, stats, 307, compact=True)
        return image
