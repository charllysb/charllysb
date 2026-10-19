"""Renders the 1024x500 Play feature graphic. Run: python3 make_feature.py feature-1024x500.png"""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H, SS = 1024, 500, 3
BG = (59, 91, 219)      # #3B5BDB, same as the launcher icon
TILE = (255, 255, 255)
FONT = "/usr/share/fonts/opentype/inter/"

img = Image.new("RGB", (W * SS, H * SS), BG)
d = ImageDraw.Draw(img)

def font(name, px):
    return ImageFont.truetype(FONT + name, px * SS)

# Icon tile on the left: white rounded square with the indigo download glyph.
tile, tx, ty = 260, 96, (H - 260) // 2
d.rounded_rectangle([tx * SS, ty * SS, (tx + tile) * SS, (ty + tile) * SS], radius=56 * SS, fill=TILE)
s = tile * SS / 108 * 1.35
cx, cy = 54, 55
ox, oy = (tx + tile / 2) * SS, (ty + tile / 2) * SS
P = lambda pts: [((x - cx) * s + ox, (y - cy) * s + oy) for x, y in pts]
d.polygon(P([(50,32),(58,32),(58,56),(67,56),(54,70),(41,56),(50,56)]), fill=BG)
d.polygon(P([(36,66),(42,66),(42,72),(66,72),(66,66),(72,66),(72,78),(36,78)]), fill=BG)

# Text block on the right.
x = 420
d.text((x * SS, 128 * SS), "Zap Saver", font=font("Inter-Bold.otf", 76), fill="white")
d.text((x * SS, 232 * SS), "Salve mídias direto na", font=font("Inter-Medium.otf", 34), fill="white")
d.text((x * SS, 276 * SS), "pasta Download", font=font("Inter-Medium.otf", 34), fill="white")

# "MP3" pill.
pill_font = font("Inter-Bold.otf", 24)
label = "+ converte áudio para MP3"
bw = d.textlength(label, font=pill_font) / SS
px, py = x, 344
d.rounded_rectangle([px * SS, py * SS, (px + bw + 40) * SS, (py + 48) * SS], radius=24 * SS, fill=(255, 255, 255))
d.text(((px + 20) * SS, (py + 11) * SS), label, font=pill_font, fill=BG)

img.resize((W, H), Image.LANCZOS).save(sys.argv[1], optimize=True)
