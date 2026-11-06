"""Color themes for the TURMO dashboard.

The renderer works with a small set of semantic colors.  A theme is just a
named set of values for those colors; every theme can be overridden from
``config.json`` via the ``theme_colors`` object.

Public API:
    THEMES          -- ordered mapping of theme id -> Theme
    resolve_theme() -- get a theme by id, with optional color overrides
    theme_choices() -- list of (id, label, description) tuples
    parse_color()   -- accept "#rrggbb", "rrggbb" or [r, g, b]
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Dict, Mapping, Optional, Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Semantic colors used by :mod:`turmo_display.render`."""

    name: str
    label: str
    description: str = ""

    bg_top: Color = (9, 13, 21)
    bg_bottom: Color = (4, 6, 11)
    grid: Color = (11, 16, 24)
    card: Color = (14, 19, 30)
    card_shadow: Color = (2, 4, 8)
    border: Color = (31, 41, 57)
    highlight: Color = (24, 33, 48)
    track: Color = (23, 31, 44)
    text: Color = (234, 240, 249)
    muted: Color = (128, 144, 168)
    dim: Color = (80, 94, 116)
    accent: Color = (34, 224, 190)
    amber: Color = (255, 179, 46)
    blue: Color = (92, 158, 255)
    green: Color = (74, 222, 128)
    red: Color = (255, 92, 96)
    plot_bg: Color = (8, 12, 19)
    plot_grid: Color = (17, 24, 36)


COLOR_FIELDS = tuple(
    field.name
    for field in fields(Theme)
    if field.name not in {"name", "label", "description"}
)
COLOR_FIELD_SET = set(COLOR_FIELDS)


def parse_color(value: Any) -> Color:
    """Convert a config color value to an ``(r, g, b)`` tuple.

    Accepted forms: ``"#22e0be"``, ``"22e0be"``, ``"#2eb"``, ``[34, 224, 190]``.
    """

    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(char * 2 for char in text)
        if len(text) != 6:
            raise ValueError(f"Neispravna boja: {value!r}")
        try:
            return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
        except ValueError as exc:
            raise ValueError(f"Neispravna boja: {value!r}") from exc

    if isinstance(value, (list, tuple)) and len(value) >= 3:
        channels = []
        for channel in value[:3]:
            try:
                number = int(channel)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Neispravna boja: {value!r}") from exc
            channels.append(max(0, min(255, number)))
        return tuple(channels)  # type: ignore[return-value]

    raise ValueError(f"Neispravna boja: {value!r}")


def _theme(
    name: str,
    label: str,
    description: str,
    colors: Mapping[str, Any],
) -> Theme:
    base = Theme(name=name, label=label, description=description)
    return replace(base, **{key: parse_color(value) for key, value in colors.items()})


# The first theme is the historical look, so existing installations keep the
# same dashboard after upgrading.
THEMES: Dict[str, Theme] = {
    "blackbox": Theme(
        name="blackbox",
        label="Blackbox",
        description="Original dark dashboard with a teal accent.",
    ),
    "nord": _theme(
        "nord",
        "Nord",
        "Cool blue-grey tones, calm and readable.",
        {
            "bg_top": "#2e3440",
            "bg_bottom": "#242933",
            "grid": "#2b303b",
            "card": "#3b4252",
            "card_shadow": "#1b1f27",
            "border": "#4c566a",
            "highlight": "#434c5e",
            "track": "#434c5e",
            "text": "#eceff4",
            "muted": "#d8dee9",
            "dim": "#81a1c1",
            "accent": "#88c0d0",
            "amber": "#ebcb8b",
            "blue": "#81a1c1",
            "green": "#a3be8c",
            "red": "#bf616a",
            "plot_bg": "#2a303b",
            "plot_grid": "#3b4252",
        },
    ),
    "dracula": _theme(
        "dracula",
        "Dracula",
        "Purple-pink night theme with strong contrast.",
        {
            "bg_top": "#282a36",
            "bg_bottom": "#1e1f29",
            "grid": "#2b2d3a",
            "card": "#343746",
            "card_shadow": "#15161d",
            "border": "#44475a",
            "highlight": "#424557",
            "track": "#44475a",
            "text": "#f8f8f2",
            "muted": "#bdc0d0",
            "dim": "#6272a4",
            "accent": "#8be9fd",
            "amber": "#f1fa8c",
            "blue": "#bd93f9",
            "green": "#50fa7b",
            "red": "#ff5555",
            "plot_bg": "#242631",
            "plot_grid": "#3a3d4d",
        },
    ),
    "gruvbox": _theme(
        "gruvbox",
        "Gruvbox",
        "Warm retro palette, easy on the eyes.",
        {
            "bg_top": "#1d2021",
            "bg_bottom": "#141617",
            "grid": "#202324",
            "card": "#282828",
            "card_shadow": "#0f1112",
            "border": "#3c3836",
            "highlight": "#32302f",
            "track": "#3c3836",
            "text": "#ebdbb2",
            "muted": "#bdae93",
            "dim": "#928374",
            "accent": "#8ec07c",
            "amber": "#fabd2f",
            "blue": "#83a598",
            "green": "#b8bb26",
            "red": "#fb4934",
            "plot_bg": "#1b1d1e",
            "plot_grid": "#32302f",
        },
    ),
    "solarized": _theme(
        "solarized",
        "Solarized",
        "The classic Solarized dark palette.",
        {
            "bg_top": "#002b36",
            "bg_bottom": "#001f27",
            "grid": "#00252e",
            "card": "#073642",
            "card_shadow": "#001820",
            "border": "#0b4a5a",
            "highlight": "#0e4b5a",
            "track": "#0e4b5a",
            "text": "#eee8d5",
            "muted": "#93a1a1",
            "dim": "#657b83",
            "accent": "#2aa198",
            "amber": "#b58900",
            "blue": "#268bd2",
            "green": "#859900",
            "red": "#dc322f",
            "plot_bg": "#00242c",
            "plot_grid": "#073642",
        },
    ),
    "light": _theme(
        "light",
        "Light",
        "Light theme for bright rooms and daylight.",
        {
            "bg_top": "#f7f9fc",
            "bg_bottom": "#e9eef5",
            "grid": "#e8edf4",
            "card": "#ffffff",
            "card_shadow": "#dce3ec",
            "border": "#d5dde8",
            "highlight": "#eef3f8",
            "track": "#e3e9f1",
            "text": "#142033",
            "muted": "#5c6b80",
            "dim": "#8a98aa",
            "accent": "#007f73",
            "amber": "#b26a00",
            "blue": "#2563eb",
            "green": "#15803d",
            "red": "#dc2626",
            "plot_bg": "#f5f8fc",
            "plot_grid": "#e2e8f0",
        },
    ),
    "mono": _theme(
        "mono",
        "Mono Green",
        "Green terminal on black, minimal look.",
        {
            "bg_top": "#050807",
            "bg_bottom": "#020403",
            "grid": "#07110c",
            "card": "#0a100d",
            "card_shadow": "#000000",
            "border": "#183326",
            "highlight": "#10251b",
            "track": "#163525",
            "text": "#d7ffe4",
            "muted": "#78b58e",
            "dim": "#3f7657",
            "accent": "#38ff9c",
            "amber": "#b6ff6a",
            "blue": "#6ad7ff",
            "green": "#38ff9c",
            "red": "#ff5c6c",
            "plot_bg": "#06100b",
            "plot_grid": "#0f2218",
        },
    ),
    "amber": _theme(
        "amber",
        "Amber CRT",
        "Warm amber CRT look, like an old monitor.",
        {
            "bg_top": "#120b04",
            "bg_bottom": "#080502",
            "grid": "#160e05",
            "card": "#1d1308",
            "card_shadow": "#060301",
            "border": "#3d2a12",
            "highlight": "#2a1d0d",
            "track": "#34230f",
            "text": "#ffe8c2",
            "muted": "#c79a58",
            "dim": "#805f31",
            "accent": "#ffb000",
            "amber": "#ffcf6b",
            "blue": "#7fc8ff",
            "green": "#8fe388",
            "red": "#ff6b5c",
            "plot_bg": "#120c05",
            "plot_grid": "#291b0b",
        },
    ),
}


def theme_choices():
    """Return ``(id, label, description)`` for every built-in theme."""

    return [(theme.name, theme.label, theme.description) for theme in THEMES.values()]


def resolve_theme(
    name: Optional[str] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Theme:
    """Resolve a theme id and apply optional color overrides.

    Unknown theme ids fall back to ``blackbox``.  Unknown override keys are
    ignored so that a config written for a newer version does not crash an
    older installation.
    """

    key = str(name or "blackbox").strip().lower()
    theme = THEMES.get(key, THEMES["blackbox"])

    if not overrides:
        return theme
    if not isinstance(overrides, Mapping):
        return theme

    values = {}
    for raw_key, raw_value in overrides.items():
        key_name = str(raw_key).strip().lower()
        if key_name not in COLOR_FIELD_SET:
            continue
        try:
            values[key_name] = parse_color(raw_value)
        except ValueError:
            continue
    return replace(theme, **values) if values else theme
