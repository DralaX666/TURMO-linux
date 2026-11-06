#!/usr/bin/env python3
"""Test pattern: checks the link and colors on a TURMO / Turing display.

    sudo /opt/turmo-display/venv/bin/python /opt/turmo-display/tools/test_pattern.py

If colored bars and the OK label appear, the hardware and protocol work.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from turmo_display.lcd import TuringRevA, find_port, list_ports_text  # noqa: E402

COLORS = [
    ("RED", (220, 40, 40)),
    ("GREEN", (40, 200, 90)),
    ("BLUE", (50, 110, 240)),
    ("YELLOW", (240, 200, 40)),
    ("CYAN", (40, 210, 210)),
    ("MAGENTA", (220, 60, 200)),
    ("WHITE", (235, 240, 250)),
    ("BLACK", (10, 14, 22)),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="auto")
    parser.add_argument("--brightness", type=int, default=90)
    args = parser.parse_args()

    print(list_ports_text())
    print("Auto-detect:", find_port() or "not found")

    lcd = TuringRevA(port=args.port)
    lcd.open()
    lcd.hello()
    lcd.set_brightness(args.brightness)
    lcd.set_orientation(0)

    width, height = lcd.get_width(), lcd.get_height()
    image = Image.new("RGB", (width, height), (6, 10, 16))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    bar_height = int(height * 0.62)
    bar_width = width // len(COLORS)
    for index, (name, color) in enumerate(COLORS):
        x0 = index * bar_width
        x1 = width if index == len(COLORS) - 1 else x0 + bar_width
        draw.rectangle((x0, 0, x1 - 1, bar_height), fill=color)
        draw.text((x0 + 6, bar_height - 18), name, font=font, fill=(0, 0, 0))

    draw.text((12, bar_height + 18), "TURMO / LINUX", font=font, fill=(0, 226, 190))
    draw.text((12, bar_height + 36), f"{lcd.model}", font=font, fill=(230, 236, 246))
    draw.text((12, bar_height + 54), f"{width} x {height}", font=font, fill=(150, 165, 185))
    draw.text((12, bar_height + 72), time.strftime("%Y-%m-%d %H:%M:%S"), font=font, fill=(110, 125, 145))
    draw.text((12, bar_height + 96), "OK", font=font, fill=(40, 200, 90))

    lcd.display_image(image)
    print("Sent. If you see the bars and OK, the link works.")
    time.sleep(0.3)
    lcd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
