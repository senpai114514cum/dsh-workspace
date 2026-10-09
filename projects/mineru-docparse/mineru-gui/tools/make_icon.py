#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成快捷方式用的图标（可重复执行）。

    python tools/make_icon.py

产物：assets/icon.ico（多尺寸：16/24/32/48/64/128/256）
设计：蓝色圆角底 + 白色纸面 + "MD"，16px 下也能认出是文档。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
BLUE = (31, 111, 235, 255)
BLUE_DARK = (18, 74, 160, 255)
WHITE = (255, 255, 255, 255)

FONTS = [
    r'C:\Windows\Fonts\arialbd.ttf',
    r'C:\Windows\Fonts\segoeuib.ttf',
    r'C:\Windows\Fonts\msyhbd.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
]


def load_font(size: int):
    for f in FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw(size: int) -> Image.Image:
    ss = 4                                  # 超采样，边缘更干净
    S = size * ss
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底
    r = int(S * 0.20)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=BLUE)
    # 底部深色带（一点层次）
    d.rounded_rectangle([0, int(S * 0.55), S - 1, S - 1], radius=r, fill=BLUE_DARK)
    d.rectangle([0, int(S * 0.55), S - 1, int(S * 0.72)], fill=BLUE_DARK)

    # 白色纸面
    m = int(S * 0.17)
    d.rounded_rectangle([m, m, S - 1 - m, S - 1 - m], radius=int(S * 0.07), fill=WHITE)

    # 折角
    c = int(S * 0.20)
    x1, y1 = S - 1 - m - c, m
    d.polygon([(x1, y1), (S - 1 - m, y1 + c), (x1, y1 + c)], fill=(196, 214, 240, 255))

    # MD 文字
    txt = 'MD'
    fs = int(S * 0.34)
    font = load_font(fs)
    box = d.textbbox((0, 0), txt, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(((S - tw) / 2 - box[0], (S - th) / 2 - box[1] + int(S * 0.09)),
           txt, font=font, fill=BLUE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = draw(256)
    out = ASSETS / 'icon.ico'
    base.save(out, format='ICO',
              sizes=[(s, s) for s in sizes],
              append_images=[draw(s) for s in sizes if s != 256])
    png = ASSETS / 'icon.png'
    base.save(png, format='PNG')
    print('已生成 %s  (%d 尺寸: %s)' % (out, len(sizes), sizes))
    print('已生成 %s  (预览用)' % png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
