"""Generates the bot's custom emoji art into emoji_assets/ (128x128 PNGs). Run: python3 tools/make_emojis.py"""
import os
from PIL import Image, ImageDraw, ImageFont
import matplotlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emoji_assets")
FONT = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data/fonts/ttf/DejaVuSans-Bold.ttf")
S = 128


def bar_segment(name, top, bottom):
    """A rounded bar segment with a top->bottom gradient and a soft highlight."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    y0, y1 = 30, 98
    for y in range(S):
        t = min(1, max(0, (y - y0) / (y1 - y0)))
        gd.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([6, y0, S - 6, y1], radius=18, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, y0 + 6, S - 14, y0 + 18], radius=6, fill=(255, 255, 255, 60))
    img.save(os.path.join(OUT, f"{name}.png"))


def medal(name, rim, face, text, txt_col):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, S - 8, S - 8], fill=rim)
    d.ellipse([22, 22, S - 22, S - 22], fill=face)
    f = ImageFont.truetype(FONT, 64)
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, 30), text, font=f, fill=txt_col)
    img.save(os.path.join(OUT, f"{name}.png"))


os.makedirs(OUT, exist_ok=True)
bar_segment("bar_g", (110, 235, 130), (30, 160, 70))
bar_segment("bar_y", (255, 225, 110), (225, 160, 20))
bar_segment("bar_r", (255, 120, 120), (200, 30, 40))
bar_segment("bar_e", (80, 84, 92), (50, 53, 60))
medal("medal_1", (190, 140, 20, 255), (255, 208, 70, 255), "1", (110, 70, 0, 255))
medal("medal_2", (130, 138, 150, 255), (215, 222, 232, 255), "2", (70, 78, 90, 255))
medal("medal_3", (140, 80, 30, 255), (214, 140, 80, 255), "3", (90, 45, 10, 255))
print(sorted(os.listdir(OUT)))
