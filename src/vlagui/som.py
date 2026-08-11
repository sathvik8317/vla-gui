"""Numbered set-of-marks renderer: draws a red box + numeric label over each detected box."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .protocols import Box


def render_som(screenshot_path: Path, boxes: list[Box], output_path: Path) -> Path:
    image = Image.open(screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()

    for i, box in enumerate(boxes):
        x0, y0 = box.x, box.y
        x1, y1 = box.x + box.width, box.y + box.height
        draw.rectangle([x0, y0, x1, y1], outline="red", width=2)

        label = str(i)
        tx0, ty0, tx1, ty1 = draw.textbbox((0, 0), label, font=font)
        tw, th = tx1 - tx0, ty1 - ty0
        draw.rectangle([x0, y0 - th - 4, x0 + tw + 4, y0], fill="red")
        draw.text((x0 + 2, y0 - th - 2), label, fill="white", font=font)

    image.save(output_path)
    return output_path
