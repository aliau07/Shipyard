"""Generated placeholder screenshots for demo comments, so no image files live in the repository."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw, ImageFont


def screenshot(caption, boxes=3, accent=(47, 93, 80), variant=0):
    """A fake app screenshot: a top bar, a row of boxes joined by arrows, and a caption."""
    image = Image.new('RGB', (1280, 800), (246, 244, 239))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 1280, 64], fill=(255, 255, 255), outline=(216, 211, 200))
    draw.rectangle([24, 20, 160, 44], fill=accent)
    left = 120 + 40 * variant
    centres = []
    for index in range(boxes):
        x = left + index * 300
        y = 300 + (60 if index % 2 else 0)
        draw.rounded_rectangle([x, y, x + 200, y + 90], radius=8, fill=(255, 255, 255), outline=accent, width=4)
        centres.append((x, y))
    for index in range(len(centres) - 1):
        (x1, y1), (x2, y2) = centres[index], centres[index + 1]
        draw.line([(x1 + 200, y1 + 45), (x2, y2 + 45)], fill=(133, 126, 114), width=4)
    font = ImageFont.load_default(size=40)
    draw.rectangle([0, 700, 1280, 800], fill=(31, 35, 40))
    draw.text((32, 726), caption, fill=(255, 255, 255), font=font)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return SimpleUploadedFile(f'screenshot-{variant}.png', buffer.getvalue(), content_type='image/png')
