"""Rebuild organizer.icns from organizer.jpg, writing it only if the pixels differ.

organizer.jpg is a full-bleed square on a solid background (its corners are not
rounded), so it is scaled to Apple's icon grid: an 824 px rounded square centred
on a transparent 1024 px canvas, with a soft shadow in the margin. The 16 and
32 px frames come from organizer-small.png, which is already a rounded square
drawn for small sizes, and fill their whole frame like the system's own icons.

The ICNS file is assembled by ``iconutil`` from an .iconset, so this script runs
on macOS only. Pillow's ICNS writer is not used because it never writes the
1x 16 and 32 px entries, which is where the small artwork matters.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
CANVAS = 1024
BODY = 824
CORNER_RADIUS = 185  # Apple's template rounds the 824 px body by about 22.4 %
SUPERSAMPLE = 4  # anti-aliases the mask
SHADOW_OFFSET = 12
SHADOW_BLUR = 14
SHADOW_ALPHA = 76
SMALL_SIZES = (16, 32)
# (name inside the .iconset, pixel size): the ten files iconutil expects.
ICONSET = [
    ("icon_16x16", 16),
    ("icon_16x16@2x", 32),
    ("icon_32x32", 32),
    ("icon_32x32@2x", 64),
    ("icon_128x128", 128),
    ("icon_128x128@2x", 256),
    ("icon_256x256", 256),
    ("icon_256x256@2x", 512),
    ("icon_512x512", 512),
    ("icon_512x512@2x", 1024),
]


def _rounded_mask(size: int, radius: int) -> Image.Image:
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * SUPERSAMPLE, fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def _master(source: Image.Image) -> Image.Image:
    """Return the 1024 px icon: masked, padded to the grid, with a soft shadow."""
    margin = (CANVAS - BODY) // 2
    mask = _rounded_mask(BODY, CORNER_RADIUS)

    shadow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, SHADOW_ALPHA), (margin, margin + SHADOW_OFFSET), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))

    body = source.convert("RGB").resize((BODY, BODY), Image.Resampling.LANCZOS).convert("RGBA")
    body.putalpha(mask)
    body_layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    body_layer.paste(body, (margin, margin))
    return Image.alpha_composite(shadow, body_layer)


def _pixels(icns: Path, workdir: Path) -> dict[str, bytes]:
    """Decode every frame of an ICNS file by round-tripping it through iconutil.

    Pillow cannot read the 1x 16 and 32 px entries iconutil writes (ic04, ic05).
    """
    iconset = workdir / f"{icns.parent.name}-{icns.stem}.iconset"
    subprocess.run(["iconutil", "--convert", "iconset", "--output", str(iconset), str(icns)], check=True)
    pixels = {}
    for png in sorted(iconset.glob("*.png")):
        with Image.open(png) as frame:
            pixels[png.name] = frame.convert("RGBA").tobytes()
    return pixels


def main() -> int:
    if shutil.which("iconutil") is None:
        print("iconutil was not found: run this script on macOS", file=sys.stderr)
        return 1
    target = Path(__file__).resolve().parent / "organizer.icns"
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "organizer.iconset"
        iconset.mkdir()
        with Image.open(ROOT / "organizer.jpg") as jpg, Image.open(ROOT / "organizer-small.png") as small:
            master = _master(jpg)
            small = small.convert("RGBA")
            for name, size in ICONSET:
                art = small if size in SMALL_SIZES else master
                art.resize((size, size), Image.Resampling.LANCZOS).save(iconset / f"{name}.png")
        fresh = Path(tmp) / "organizer.icns"
        subprocess.run(["iconutil", "--convert", "icns", "--output", str(fresh), str(iconset)], check=True)
        # Compare decoded pixels: PNG compression bytes can differ between platforms.
        if target.exists() and _pixels(fresh, Path(tmp)) == _pixels(target, Path(tmp)):
            print(f"{target.name} is up to date")
            return 0
        target.write_bytes(fresh.read_bytes())
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
