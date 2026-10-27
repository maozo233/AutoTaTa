"""Generate PNG/ICO sizes from the approved Figma wordmark export."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/figma/app-wordmark-0.1.38.png"


def render(size):
    # Figma is the source of truth: preserve the user's edited wordmark.
    return Image.open(SOURCE).convert("RGBA").resize(
        (size, size), Image.Resampling.LANCZOS
    )


if __name__ == "__main__":
    render(1024).save(ROOT / "assets/app-icon.png")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [render(size) for size in sizes]
    frames[-1].save(
        ROOT / "assets/app.ico", sizes=[(s, s) for s in sizes],
        append_images=frames[:-1],
    )
    preview = Image.new("RGB", (480, 300), "#f4e8d1")
    large = render(256)
    preview.paste(large, (16, 20), large)
    draw = ImageDraw.Draw(preview)
    for y, size in ((30, 64), (125, 32), (190, 24), (245, 16)):
        frame = render(size)
        preview.paste(frame, (315, y), frame)
        draw.text((395, y + size / 2 - 5), f"{size}px", fill="#101d42")
    preview.save(ROOT / "design/app-icon-preview.png")
