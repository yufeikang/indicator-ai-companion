#!/usr/bin/env -S uv run --with fonttools python
"""从 macOS 系统字体提取单 face TTF 供 ESPHome 使用(优先 PingFang SC 苹方)。

ChineseFont.ttf 含字体版权,不入库;在本机用本脚本重建:
    uv run --with fonttools firmware/fonts/extract-font.py
"""
import glob
import os

from fontTools.ttLib import TTCollection

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChineseFont.ttf")


def _pingfang_paths():
    paths = sorted(glob.glob("/System/Library/AssetsV2/**/PingFang.ttc", recursive=True))
    paths.append("/System/Library/Fonts/PingFang.ttc")
    return [p for p in paths if os.path.exists(p)]


# (字体文件, 期望 face 名关键词);PingFang SC 优先,退回 Hiragino / STHeiti
SOURCES = [(p, "PingFang SC") for p in _pingfang_paths()] + [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", None),
    ("/System/Library/Fonts/STHeiti Medium.ttc", None),
]
_SKIP = ("Medium", "Semibold", "Light", "Thin", "Ultralight")

for src, want in SOURCES:
    if not os.path.exists(src):
        continue
    ttc = TTCollection(src)
    faces = [(i, f["name"].getDebugName(4)) for i, f in enumerate(ttc.fonts)]
    if want:
        idx = next((i for i, n in faces if n and want in n and not any(w in n for w in _SKIP)), None)
    else:
        idx = 0
    if idx is None:
        continue
    ttc.fonts[idx].save(OUT)
    print(f"saved {OUT}\n  from {src} (face {idx}: {faces[idx][1]})")
    break
else:
    raise SystemExit("未找到系统中文字体")
