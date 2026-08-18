from pathlib import Path

from PIL import Image, ImageDraw


out = Path("app_icon.ico")
preview = Path("app_icon_preview.png")

size = 256
base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(base)

red = (215, 7, 18, 255)
charcoal = (49, 54, 57, 255)
white = (255, 255, 255, 255)

draw.rounded_rectangle((18, 18, 238, 238), radius=54, fill=white)
draw.rounded_rectangle((18, 18, 238, 238), radius=54, outline=(220, 226, 230, 255), width=5)

draw.ellipse((52, 46, 198, 192), fill=charcoal)
draw.ellipse((84, 78, 166, 160), fill=white)
draw.polygon([(139, 139), (211, 206), (166, 206), (111, 154)], fill=charcoal)

draw.rounded_rectangle((168, 46, 226, 80), radius=5, fill=red)
draw.rounded_rectangle((190, 46, 226, 166), radius=5, fill=red)

base.save(preview)
base.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(out.resolve())
