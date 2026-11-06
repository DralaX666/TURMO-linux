#!/usr/bin/env python3
"""Generate preview PNGs for every built-in theme."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from turmo_display.render import Renderer  # noqa: E402
from turmo_display.stats import DemoSampler  # noqa: E402
from turmo_display.themes import THEMES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview all TURMO themes")
    parser.add_argument("directory", nargs="?", default="docs/themes")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()

    os.makedirs(args.directory, exist_ok=True)
    stats = DemoSampler().sample()
    for name in THEMES:
        image = Renderer(
            args.width,
            args.height,
            options={"theme": name},
        ).render(stats)
        path = os.path.join(args.directory, f"{name}.png")
        image.save(path)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
