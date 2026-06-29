import os

import numpy as np
from PIL import Image

W, H = 128, 64
N = 18
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "eye")
os.makedirs(OUT, exist_ok=True)

EYES = [(40, 32), (88, 32)]   # 左右眼中心
R = 22                         # 眼半径
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

C_IRIS_IN = np.array([180, 235, 255], np.float32)   # 虹膜内亮青
C_IRIS_OUT = np.array([40, 130, 200], np.float32)    # 虹膜外深青
C_PUPIL = np.array([10, 22, 40], np.float32)         # 瞳孔深


def frame(openness, look_x, look_y):
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    for (ex, ey) in EYES:
        d = np.sqrt((xx - ex) ** 2 + (yy - ey) ** 2)
        # 虹膜径向渐变
        t = np.clip(d / R, 0, 1)
        iris = C_IRIS_IN[None, None] * (1 - t[..., None]) + C_IRIS_OUT[None, None] * t[..., None]
        eye_mask = d <= R
        # 瞳孔(随视线偏移)
        px, py = ex + look_x, ey + look_y
        dp = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
        pupil_mask = dp <= R * 0.45
        col = np.where(pupil_mask[..., None], C_PUPIL[None, None], iris)
        # 高光白点(偏左上)
        dh = np.sqrt((xx - (px - 6)) ** 2 + (yy - (py - 6)) ** 2)
        hl = np.clip(1 - dh / 5, 0, 1)[..., None]
        col = col * (1 - hl) + np.array([255, 255, 255], np.float32)[None, None] * hl
        # 眼睑开合:可见高度 = openness * R(上下被眼睑盖)
        lid_mask = np.abs(yy - ey) <= (openness * R)
        m = eye_mask & lid_mask
        rgb[m] = col[m]
        alpha[m] = 255.0
    out = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha.astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


# 时间线:长睁(偶尔扫视)-> 快速眨眼
seq = []
for _ in range(6):
    seq.append((1.0, 0, 0))            # 睁,居中
seq += [(1.0, -7, 0), (1.0, -7, 0)]    # 看左
seq += [(1.0, 0, 0), (1.0, 0, 0)]      # 回中
seq += [(1.0, 7, 0), (1.0, 7, 0)]      # 看右
seq += [(1.0, 0, 0)]                   # 回中
seq += [(0.55, 0, 0), (0.15, 0, 0), (0.55, 0, 0)]   # 眨眼(快)
seq += [(1.0, 0, 0)]                   # 睁
N = len(seq)

for i, (op, lx, ly) in enumerate(seq):
    frame(op, lx, ly).save(f"{OUT}/eye_{i:02d}.png")

strip = Image.new("RGBA", (W * N, H), (14, 26, 44, 255))
for i in range(N):
    strip.alpha_composite(Image.open(f"{OUT}/eye_{i:02d}.png"), (i * W, 0))
strip.convert("RGB").save(os.path.join(HERE, "eye_strip_preview.png"))
print(f"{N} frames @ {W}x{H} -> {OUT}")
