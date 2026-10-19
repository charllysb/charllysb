import sys
from PIL import Image, ImageDraw
BG = (59, 91, 219)  # #3B5BDB indigo, deliberately unlike WhatsApp's green
SS = 4
def render(size, scale_boost, out):
    N = size * SS
    img = Image.new("RGB", (N, N), BG)
    d = ImageDraw.Draw(img)
    s = N / 108 * scale_boost
    cx, cy = 54, 55  # glyph centre in the 108 viewport
    def P(pts):
        return [((x - cx) * s + N / 2, (y - cy) * s + N / 2) for x, y in pts]
    arrow = [(50,32),(58,32),(58,56),(67,56),(54,70),(41,56),(50,56)]
    tray = [(36,66),(42,66),(42,72),(66,72),(66,66),(72,66),(72,78),(36,78)]
    d.polygon(P(arrow), fill="white")
    d.polygon(P(tray), fill="white")
    img.resize((size, size), Image.LANCZOS).save(out, optimize=True)
render(512, 1.35, sys.argv[1])
