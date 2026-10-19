"""Frames raw phone screenshots into 1080x1920 (9:16) Play Store images with a caption.

Usage: python3 make_screenshots.py OUT_DIR "Legenda 1" shot1.png "Legenda 2" shot2.png ...
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (59, 91, 219)  # app indigo
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
CAPTION_TOP, CAPTION_SIZE, LINE_GAP = 110, 64, 16
SHOT_TOP, MARGIN, RADIUS = 380, 90, 40


def wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def frame(caption, shot_path, out_path):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT, CAPTION_SIZE)
    y = CAPTION_TOP
    for line in wrap(d, caption, font, W - 2 * MARGIN):
        d.text(((W - d.textlength(line, font=font)) / 2, y), line, font=font, fill="white")
        y += CAPTION_SIZE + LINE_GAP

    shot = Image.open(shot_path).convert("RGB")
    max_w, max_h = W - 2 * MARGIN, H - SHOT_TOP - 60
    scale = min(max_w / shot.width, max_h / shot.height)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.LANCZOS)

    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *shot.size], radius=RADIUS, fill=255)
    x = (W - shot.width) // 2
    canvas.paste(shot, (x, SHOT_TOP), mask)
    canvas.save(out_path, optimize=True)


if __name__ == "__main__":
    out_dir, pairs = sys.argv[1], sys.argv[2:]
    os.makedirs(out_dir, exist_ok=True)
    for i in range(0, len(pairs), 2):
        frame(pairs[i], pairs[i + 1], os.path.join(out_dir, f"screenshot-{i // 2 + 1}.png"))
