"""Rebuild organizer.ico from organizer.jpg, writing it only if the pixels differ.

The 16-32 px frames come from organizer-small.png, a 512 px render of
organizer-small.svg (rendered once with cairosvg, so Windows needs no Cairo).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
SMALL_SIZES = (16, 24, 32)


def _pixels(path: Path) -> dict[tuple[int, int], bytes]:
    with Image.open(path) as ico:
        return {s: ico.ico.getimage(s).convert("RGBA").tobytes() for s in sorted(ico.info["sizes"])}


def main() -> int:
    source = ROOT / "organizer.jpg"
    target = ROOT / "organizer.ico"
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "organizer.ico"
        with Image.open(source) as img, Image.open(ROOT / "organizer-small.png") as small:
            small = small.convert("RGBA")
            frames = [small.resize((s, s), Image.Resampling.LANCZOS) for s in SMALL_SIZES]
            base = img.convert("RGBA")
            # Pillow scales sizes without a matching frame from the last image, so the JPG goes last.
            base.save(fresh, format="ICO", sizes=SIZES, append_images=[*frames, base])
        # Compare decoded pixels: PNG compression bytes differ between platforms.
        if target.exists() and _pixels(fresh) == _pixels(target):
            print(f"{target.name} is up to date")
            return 0
        target.write_bytes(fresh.read_bytes())
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
