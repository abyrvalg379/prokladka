# -*- coding: utf-8 -*-
"""Генератор обложки PROKLADKA (vverh-стиль: скруглённый прямоугольник, синяя
рамка, Century Gothic). Заголовок вписывается в рамку по ширине; бейдж
EXPORT BETA — правый верхний угол.

Запуск: python build_logo.py
Обновляет assets/prokladka_logo.png и work/logo/prokladka_logo.png.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 512
MARGIN = 44
RADIUS = 64
OUTLINE = 6
BLUE = (91, 155, 213, 255)
FILL = (45, 45, 45, 255)
TITLE_COL = (224, 224, 224, 255)
SUB_COL = (140, 140, 140, 255)
BADGE_BG = (192, 57, 43, 255)
BADGE_TX = (245, 245, 245, 255)
TITLE = "PROKLADKA"
SUB = "Blender  <->  Maya  FBX  Bridge"
BADGE = "EXPORT BETA"

GOTHIC = r"C:\Windows\Fonts\GOTHIC.TTF"
GOTHICB = r"C:\Windows\Fonts\GOTHICB.TTF"


def tracked_width(draw, text, font, tracking):
    w = draw.textlength(text, font=font)
    return w + tracking * max(0, len(text) - 1)


def draw_tracked(draw, xy, text, font, tracking, fill):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def fit_font(draw, text, path, max_w, start_size, tracking_ratio=0.06):
    size = start_size
    while size > 20:
        font = ImageFont.truetype(path, size)
        tracking = size * tracking_ratio
        if tracked_width(draw, text, font, tracking) <= max_w:
            return font, tracking
        size -= 2
    return ImageFont.truetype(path, 20), 20 * tracking_ratio


img = Image.new("RGBA", (W, H), (24, 26, 28, 255))
d = ImageDraw.Draw(img)

# Скруглённый прямоугольник с синей рамкой
d.rounded_rectangle(
    [MARGIN, MARGIN, W - MARGIN, H - MARGIN],
    radius=RADIUS, fill=FILL, outline=BLUE, width=OUTLINE)

pad = 70
inner_w = (W - 2 * MARGIN) - 2 * pad

# Заголовок: вписать в ширину рамки
title_font, tracking = fit_font(d, TITLE, GOTHICB, inner_w, 150)
tw = tracked_width(d, TITLE, title_font, tracking)
th = title_font.size
tx = (W - tw) / 2
ty = H * 0.30 - th / 2
draw_tracked(d, (tx, ty), TITLE, title_font, tracking, TITLE_COL)

# Сабтайтл
sub_font = ImageFont.truetype(GOTHIC, 44)
sw = d.textlength(SUB, font=sub_font)
d.text(((W - sw) / 2, H * 0.62), SUB, font=sub_font, fill=SUB_COL)

# Бейдж EXPORT BETA — правый верхний угол, внутри рамки
badge_font = ImageFont.truetype(GOTHICB, 30)
bw = d.textlength(BADGE, font=badge_font)
bpad_x, bpad_y = 18, 10
bx1 = W - MARGIN - 46 - bw - 2 * bpad_x
by1 = MARGIN + 40
bx2, by2 = bx1 + bw + 2 * bpad_x, by1 + badge_font.size + 2 * bpad_y
d.rounded_rectangle([bx1, by1, bx2, by2], radius=12, fill=BADGE_BG)
d.text((bx1 + bpad_x, by1 + bpad_y - 2), BADGE, font=badge_font, fill=BADGE_TX)

out1 = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "prokladka_logo.png"))
out2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prokladka_logo.png")
img.convert("RGB").save(out1)
img.convert("RGB").save(out2)
print("saved:", out1)
