"""R11 #8: build relay.ico from the line-family mark (ui/index.html #i-mark).

Accent-green line on a dark rounded square. Supersampled, then downscaled
per size. Run:  python tools/make_icon.py   (needs Pillow)
"""
import math
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GREEN = (61, 220, 151, 255)   # --ok
TILE = (20, 25, 34, 255)      # dark square
EDGE = (40, 48, 62, 255)


def mark_paths():
    html = open(os.path.join(ROOT, "ui", "index.html"), encoding="utf-8").read()
    sym = re.search(r'<symbol id="i-mark".*?</symbol>', html, re.S).group(0)
    paths = re.findall(r' d="([^"]+)"', sym)
    circles = [tuple(map(float, c)) for c in re.findall(r'cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', sym)]
    return paths, circles


def flatten(d):
    """Polylines for M/L/H/V/C/A (abs+rel). Arcs here are semicircles."""
    toks = re.findall(r"[A-Za-z]|-?\d*\.?\d+", d)
    out, cur, x, y, i, cmd = [], None, 0.0, 0.0, 0, None
    def num():
        nonlocal i
        v = float(toks[i]); i += 1; return v
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]; i += 1
        rel = cmd.islower(); c = cmd.upper()
        if c == "M":
            dx, dy = num(), num()
            x, y = (x + dx, y + dy) if rel else (dx, dy)
            cur = [(x, y)]; out.append(cur); cmd = "l" if rel else "L"
        elif c in "LHV":
            if c == "L":
                dx, dy = num(), num(); x, y = (x + dx, y + dy) if rel else (dx, dy)
            elif c == "H":
                v = num(); x = x + v if rel else v
            else:
                v = num(); y = y + v if rel else v
            cur.append((x, y))
        elif c == "C":
            p = [num() for _ in range(6)]
            if rel:
                p = [p[0] + x, p[1] + y, p[2] + x, p[3] + y, p[4] + x, p[5] + y]
            x0, y0 = x, y
            for k in range(1, 17):
                t = k / 16; u = 1 - t
                cur.append((u**3*x0 + 3*u*u*t*p[0] + 3*u*t*t*p[2] + t**3*p[4],
                            u**3*y0 + 3*u*u*t*p[1] + 3*u*t*t*p[3] + t**3*p[5]))
            x, y = p[4], p[5]
        elif c == "A":
            _rx, _ry, _rot, _large, sweep, ex, ey = [num() for _ in range(7)]
            if rel:
                ex, ey = ex + x, ey + y
            cx, cy = (x + ex) / 2, (y + ey) / 2
            r = math.hypot(ex - x, ey - y) / 2
            a0 = math.atan2(y - cy, x - cx)
            sgn = 1 if sweep else -1
            for k in range(1, 17):
                a = a0 + sgn * math.pi * k / 16
                cur.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            x, y = ex, ey
    return out


def render(size):
    ss = 8; S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    rad = S * 0.22
    dr.rounded_rectangle([0, 0, S - 1, S - 1], rad, fill=EDGE)
    b = max(ss, S // 64)
    dr.rounded_rectangle([b, b, S - 1 - b, S - 1 - b], rad - b, fill=TILE)
    pad = S * 0.16; k = (S - 2 * pad) / 20
    stroke = 1.2 if size >= 48 else 1.6 if size >= 24 else 2.0  # keep it legible small
    w = max(1, round(stroke * k))
    P = lambda p: (pad + p[0] * k, pad + p[1] * k)
    paths, circles = mark_paths()
    for d in paths:
        for poly in flatten(d):
            pts = [P(p) for p in poly]
            dr.line(pts, fill=GREEN, width=w, joint="curve")
            for q in (pts[0], pts[-1]):
                dr.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=GREEN)
    for cx, cy, r in circles:
        c = P((cx, cy)); rr = r * k
        dr.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=GREEN, width=w)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [render(s) for s in sizes]
    ico = os.path.join(ROOT, "relay.ico")
    imgs[-1].save(ico, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    imgs[-1].save(os.path.join(ROOT, "docs", "relay-icon-256.png"))
    print("wrote", ico)
