"""生成 Claude 官方星芒(spark)动画帧 —— session 图标。

形状取自官方 Claude 品牌 mark(claude-logo.svg, viewBox 24x24),白色实心、透明底,
靠 LVGL image_recolor 在设备端按状态上色。工作中(run/think)时设备让 animimg 连续
播放 = 轻微呼吸脉动(缩放),logo 始终正向、保持原样;空闲时停在第 0 帧 = 静态。
脉动用 cos 缓动,首尾无缝循环。

依赖渲染: uv run --with cairosvg --with pillow python gen-claude.py
"""
import io
import math
import os

import cairosvg
from PIL import Image

SIZE = 44          # 输出边长(px)
N = 12             # 帧数
S_MIN = 0.62       # 呼吸最小缩放
S_MAX = 1.00       # 呼吸最大缩放
MARGIN = 1         # 满缩放时四周留白(px)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "claude")
SVG = os.path.join(HERE, "claude-logo.svg")
os.makedirs(OUT, exist_ok=True)

# 把官方 logo 渲成白色高分辨率母版,后续按帧缩放保证清晰
_base_px = (SIZE - 2 * MARGIN) * 4
_svg = open(SVG).read().replace("<path ", '<path fill="#FFFFFF" ')
_png = cairosvg.svg2png(bytestring=_svg.encode(), output_width=_base_px, output_height=_base_px)
MASTER = Image.open(io.BytesIO(_png)).convert("RGBA")


def frame(scale):
    side = max(1, int(round((SIZE - 2 * MARGIN) * scale)))
    logo = MASTER.resize((side, side), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    off = (SIZE - side) // 2
    canvas.alpha_composite(logo, (off, off))
    return canvas


for i in range(N):
    # cos 缓动: i=0 最小, i=N/2 最大, 回到最小 —— 无缝呼吸
    t = 0.5 - 0.5 * math.cos(2 * math.pi * i / N)
    scale = S_MIN + (S_MAX - S_MIN) * t
    frame(scale).save(os.path.join(OUT, f"claude_{i:02d}.png"))

print(f"wrote {N} frames -> {OUT}")
