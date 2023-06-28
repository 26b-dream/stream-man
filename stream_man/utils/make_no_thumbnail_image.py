"""Use pillow to make an image that says "No Thumbnail"."""
import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611
from common.constants import BASE_DIR
from PIL import Image, ImageDraw, ImageFont

image = Image.new("RGB", (480, 270), "grey")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("Keyboard.ttf", 64)

text = "No Thumbnail"

# Calculate the position to center the text
text_box = draw.textbbox((0, 0), text, font=font)
x = (image.width - text_box[2]) / 2
y = (image.height - text_box[3]) / 2

draw.text((x, y), text, font=font, fill="black")

image.save(BASE_DIR / "static" / "no_thumbnail.png")
