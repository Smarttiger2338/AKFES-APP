from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
OUTPUT = ASSETS / "akfes.ico"


def build_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = max(2, size // 14)
    radius = max(4, size // 5)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=(20, 112, 255, 255),
    )

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (size * 0.18, size * 0.08, size * 0.86, size * 0.72),
        fill=(120, 190, 255, 90),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(max(1, size // 12)))
    image.alpha_composite(glow)

    draw = ImageDraw.Draw(image)
    shield = [
        (size * 0.50, size * 0.18),
        (size * 0.75, size * 0.28),
        (size * 0.72, size * 0.60),
        (size * 0.50, size * 0.82),
        (size * 0.28, size * 0.60),
        (size * 0.25, size * 0.28),
    ]
    draw.polygon(shield, fill=(8, 30, 68, 220))

    stroke = max(2, size // 18)
    draw.line(
        [(size * 0.36, size * 0.62), (size * 0.50, size * 0.34), (size * 0.64, size * 0.62)],
        fill=(255, 255, 255, 255),
        width=stroke,
        joint="curve",
    )
    draw.line(
        [(size * 0.41, size * 0.53), (size * 0.59, size * 0.53)],
        fill=(255, 255, 255, 255),
        width=stroke,
    )
    return image


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [build_icon(size) for size in sizes]
    images[-1].save(OUTPUT, format="ICO", sizes=[(size, size) for size in sizes], append_images=images[:-1])
    print(f"Icon created: {OUTPUT}")


if __name__ == "__main__":
    main()
