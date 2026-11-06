"""TURMO / Turing Smart Screen Linux dashboard."""

from .themes import THEMES, Theme, resolve_theme, theme_choices

__all__ = ["THEMES", "Theme", "resolve_theme", "theme_choices", "__version__"]
__version__ = "1.4.0"
