from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ICONSET = ASSETS / "app_icon.iconset"


def rounded_rectangle_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def draw_icon(size: int) -> Image.Image:
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    inset = int(70 * scale)
    radius = int(190 * scale)
    shadow_draw.rounded_rectangle(
        (inset, inset + int(22 * scale), size - inset, size - inset + int(22 * scale)),
        radius=radius,
        fill=(15, 20, 26, 58),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(28 * scale)))
    image.alpha_composite(shadow)

    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    body_draw = ImageDraw.Draw(body)
    body_draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=radius,
        fill=(244, 246, 247, 255),
        outline=(224, 228, 231, 255),
        width=max(1, int(2 * scale)),
    )
    image.alpha_composite(body)

    draw = ImageDraw.Draw(image)
    black = (29, 36, 43, 255)
    slate = (72, 91, 108, 255)
    blue = (111, 137, 165, 255)
    dark_blue = (78, 104, 128, 255)

    left = int(280 * scale)
    top = int(270 * scale)
    cell = int(84 * scale)
    gap = int(42 * scale)
    rows = [top + row * (cell + gap) for row in range(4)]
    cols = [left + col * (cell + gap) for col in range(3)]

    for row_index, y in enumerate(rows):
        for col_index, x in enumerate(cols):
            color = black if col_index < 2 else (slate if row_index % 2 == 0 else black)
            draw.rectangle((x, y, x + cell, y + cell), fill=color)

    scatter_specs = [
        (640, 272, 52, blue),
        (720, 278, 38, dark_blue),
        (642, 402, 42, blue),
        (730, 430, 30, dark_blue),
        (638, 532, 32, blue),
        (722, 570, 24, dark_blue),
        (648, 660, 24, blue),
        (730, 690, 18, dark_blue),
    ]
    for x, y, box, color in scatter_specs:
        x1 = int(x * scale)
        y1 = int(y * scale)
        b = int(box * scale)
        draw.rectangle((x1, y1, x1 + b, y1 + b), fill=color)

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
    source = draw_icon(1024)
    source.save(ASSETS / "app_icon.png")
    source.save(
        ASSETS / "app_icon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for filename, size in sizes.items():
        source.resize((size, size), Image.Resampling.LANCZOS).save(ICONSET / filename)


if __name__ == "__main__":
    save_iconset()
