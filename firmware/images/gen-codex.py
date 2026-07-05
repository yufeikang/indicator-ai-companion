"""Generate Codex session icon frames.

The firmware recolors these white/alpha PNGs at runtime. The animation is a
small breathing pulse around a compact bracketed prompt mark.

No third-party package is required:
    uv run python firmware/images/gen-codex.py
"""
import math
import os
import struct
import zlib

SIZE = 44
SCALE = 4
N = 12
S_MIN = 0.62
S_MAX = 1.00
MARGIN = 1
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "codex")
os.makedirs(OUT, exist_ok=True)


def _point_in_poly(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, pi in enumerate(points):
        pj = points[j]
        if ((pi[1] > y) != (pj[1] > y)) and (
            x < (pj[0] - pi[0]) * (y - pi[1]) / (pj[1] - pi[1]) + pi[0]
        ):
            inside = not inside
        j = i
    return inside


def _draw_poly(mask: list[int], points: list[tuple[float, float]]) -> None:
    w = SIZE * SCALE
    min_x = max(0, int(math.floor(min(x for x, _ in points))))
    max_x = min(w - 1, int(math.ceil(max(x for x, _ in points))))
    min_y = max(0, int(math.floor(min(y for _, y in points))))
    max_y = min(w - 1, int(math.ceil(max(y for _, y in points))))
    for y in range(min_y, max_y + 1):
        row = y * w
        for x in range(min_x, max_x + 1):
            if _point_in_poly(x + 0.5, y + 0.5, points):
                mask[row + x] = 255


def _draw_circle(mask: list[int], cx: float, cy: float, r: float) -> None:
    w = SIZE * SCALE
    rr = r * r
    min_x = max(0, int(math.floor(cx - r)))
    max_x = min(w - 1, int(math.ceil(cx + r)))
    min_y = max(0, int(math.floor(cy - r)))
    max_y = min(w - 1, int(math.ceil(cy + r)))
    for y in range(min_y, max_y + 1):
        row = y * w
        for x in range(min_x, max_x + 1):
            dx = x + 0.5 - cx
            dy = y + 0.5 - cy
            if dx * dx + dy * dy <= rr:
                mask[row + x] = 255


def _draw_segment(mask: list[int], ax: float, ay: float, bx: float, by: float, r: float) -> None:
    w = SIZE * SCALE
    vx = bx - ax
    vy = by - ay
    vv = vx * vx + vy * vy
    min_x = max(0, int(math.floor(min(ax, bx) - r)))
    max_x = min(w - 1, int(math.ceil(max(ax, bx) + r)))
    min_y = max(0, int(math.floor(min(ay, by) - r)))
    max_y = min(w - 1, int(math.ceil(max(ay, by) + r)))
    rr = r * r
    for y in range(min_y, max_y + 1):
        row = y * w
        for x in range(min_x, max_x + 1):
            px = x + 0.5
            py = y + 0.5
            t = 0.0 if vv == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / vv))
            dx = px - (ax + t * vx)
            dy = py - (ay + t * vy)
            if dx * dx + dy * dy <= rr:
                mask[row + x] = 255


def _png_rgba(path: str, pixels: bytes, width: int, height: int) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(data)


def frame(scale: float) -> bytes:
    hi = SIZE * SCALE
    mask = [0] * (hi * hi)
    center = hi / 2
    half = (SIZE - 2 * MARGIN) * SCALE * scale / 2

    stroke = max(1.6 * SCALE, half * 0.13)
    sx = half / 18.0
    sy = half / 18.0

    def pt(x: float, y: float) -> tuple[float, float]:
        return center + x * sx, center + y * sy

    # Bracketed prompt mark, matching Codex's terminal-oriented visual language.
    for a, b in (
        (pt(-13.0, -9.0), pt(-8.0, -9.0)),
        (pt(-13.0, -9.0), pt(-13.0, 9.0)),
        (pt(-13.0, 9.0), pt(-8.0, 9.0)),
        (pt(13.0, -9.0), pt(8.0, -9.0)),
        (pt(13.0, -9.0), pt(13.0, 9.0)),
        (pt(13.0, 9.0), pt(8.0, 9.0)),
        (pt(-3.5, -5.0), pt(1.5, 0.0)),
        (pt(1.5, 0.0), pt(-3.5, 5.0)),
        (pt(4.5, 6.0), pt(9.5, 6.0)),
    ):
        _draw_segment(mask, a[0], a[1], b[0], b[1], stroke)

    # Downsample by box average into RGBA.
    out = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            total = 0
            for yy in range(SCALE):
                row = (y * SCALE + yy) * hi
                for xx in range(SCALE):
                    total += mask[row + x * SCALE + xx]
            a = total // (SCALE * SCALE)
            out.extend((255, 255, 255, a))
    return bytes(out)


for i in range(N):
    t = 0.5 - 0.5 * math.cos(2 * math.pi * i / N)
    scale = S_MIN + (S_MAX - S_MIN) * t
    _png_rgba(os.path.join(OUT, f"codex_{i:02d}.png"), frame(scale), SIZE, SIZE)

print(f"wrote {N} frames -> {OUT}")
