from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ICONSET = ASSETS / "app_icon.iconset"


def build_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (int(size * 0.12), int(size * 0.12), int(size * 0.88), int(size * 0.88)),
        fill=(0, 137, 184, 210),
    )
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(int(size * 0.1))))

    draw = ImageDraw.Draw(image)
    cyan = (0, 137, 184, 255)
    black = (0, 0, 0, 255)
    line = max(2, int(size * 0.018))

    def rect(x: float, y: float, w: float, h: float, fill: tuple[int, int, int, int], outline: bool = False) -> None:
        box = (
            int(size * x),
            int(size * y),
            int(size * (x + w)),
            int(size * (y + h)),
        )
        if outline:
            draw.rectangle(box, outline=fill, width=line)
        else:
            draw.rectangle(box, fill=fill)

    rect(0.18, 0.22, 0.42, 0.05, cyan, outline=True)
    rect(0.66, 0.22, 0.16, 0.05, cyan, outline=True)
    rect(0.18, 0.34, 0.34, 0.06, black)
    rect(0.56, 0.34, 0.26, 0.06, black)
    rect(0.18, 0.48, 0.18, 0.06, black)
    rect(0.42, 0.48, 0.32, 0.06, cyan, outline=True)
    rect(0.18, 0.62, 0.50, 0.06, black)
    rect(0.73, 0.62, 0.09, 0.06, cyan, outline=True)
    rect(0.18, 0.76, 0.13, 0.06, black)
    rect(0.38, 0.76, 0.36, 0.06, cyan, outline=True)

    return image


def save_iconset() -> None:
    ASSETS.mkdir(exist_ok=True)
    ICONSET.mkdir(exist_ok=True)
    sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    source = build_icon(1024)
    source.save(ASSETS / "app_icon.png")
    source.save(
        ASSETS / "app_icon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for filename, size in sizes.items():
        source.resize((size, size), Image.Resampling.LANCZOS).save(ICONSET / filename)


if __name__ == "__main__":
    save_iconset()
