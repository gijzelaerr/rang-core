"""Render the text-free marks in docs/logo/ to PNG and favicon.ico.

Run once after an SVG changes and commit the renders:

    python docs/logo/render.py

Needs `resvg-py` (resvg's Rust renderer in a self-contained wheel, no
system cairo) and Pillow, both from public PyPI. The wordmark and lockup
SVGs are not rasterised: they set their text in Inter, which a renderer
without that font replaces silently, so the site uses those SVGs directly
and lets the browser pick the font.
"""

import io
from pathlib import Path

import resvg_py
from PIL import Image

HERE = Path(__file__).resolve().parent
SIZES = {
    "logo": (128, 256, 512),
    "icon": (16, 32, 48, 64, 128, 180, 256),
    "icon-mono": (16, 32, 48),
}
FAVICON = ("icon", (16, 32, 48, 64))


def render(name, size):
    png = resvg_py.svg_to_bytes(
        svg_path=str(HERE / f"{name}.svg"),
        width=size,
        height=size,
        skip_system_fonts=True,
    )
    return bytes(png)


def main():
    for name, sizes in SIZES.items():
        for size in sizes:
            (HERE / f"{name}-{size}.png").write_bytes(render(name, size))
    name, sizes = FAVICON
    largest = Image.open(io.BytesIO(render(name, max(sizes))))
    largest.save(HERE / "favicon.ico", format="ICO", sizes=[(s, s) for s in sizes])


if __name__ == "__main__":
    main()
