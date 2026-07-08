"""
icons.py — Pillow uchun sodda, toza chiziqli ikonkalar (emoji o'rniga).
Har biri markazi (cx, cy), o'lchami r bilan chiziladi. Rang beriladi.
"""

from PIL import ImageDraw


def draw(d: ImageDraw.ImageDraw, name: str, cx: int, cy: int, r: int, color, w: int = 3):
    fn = _MAP.get(name, _target)
    fn(d, cx, cy, r, color, w)


def _target(d, cx, cy, r, c, w):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=w)
    d.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], outline=c, width=w)
    d.ellipse([cx - r * 0.12, cy - r * 0.12, cx + r * 0.12, cy + r * 0.12], fill=c)


def _sales(d, cx, cy, r, c, w):
    # yuqoriga o'q (savdo o'sishi)
    d.line([(cx - r, cy + r * 0.6), (cx - r * 0.2, cy - r * 0.1),
            (cx + r * 0.3, cy + r * 0.3), (cx + r, cy - r * 0.7)], fill=c, width=w, joint="curve")
    d.line([(cx + r * 0.45, cy - r * 0.7), (cx + r, cy - r * 0.7)], fill=c, width=w)
    d.line([(cx + r, cy - r * 0.7), (cx + r, cy - r * 0.2)], fill=c, width=w)


def _kpi(d, cx, cy, r, c, w):
    # gauge (yarim halqa + strelka)
    d.arc([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=c, width=w)
    d.line([(cx, cy), (cx + r * 0.6, cy - r * 0.5)], fill=c, width=w)
    d.ellipse([cx - r * 0.14, cy - r * 0.14, cx + r * 0.14, cy + r * 0.14], fill=c)


def _debt(d, cx, cy, r, c, w):
    # ogohlantirish uchburchagi
    d.line([(cx, cy - r), (cx - r, cy + r * 0.8), (cx + r, cy + r * 0.8), (cx, cy - r)],
           fill=c, width=w, joint="curve")
    d.line([(cx, cy - r * 0.3), (cx, cy + r * 0.25)], fill=c, width=w)
    d.ellipse([cx - w * 0.7, cy + r * 0.45, cx + w * 0.7, cy + r * 0.45 + w * 1.4], fill=c)


def _growth(d, cx, cy, r, c, w):
    # o'suvchi ustunlar
    bw = r * 0.5
    for i, h in enumerate((0.4, 0.75, 1.15)):
        x = cx - r + i * (bw + r * 0.18)
        d.rectangle([x, cy + r - r * h, x + bw, cy + r], fill=c)


def _flag(d, cx, cy, r, c, w):
    d.line([(cx - r * 0.6, cy - r), (cx - r * 0.6, cy + r)], fill=c, width=w)
    d.polygon([(cx - r * 0.6, cy - r), (cx + r * 0.8, cy - r * 0.5),
               (cx - r * 0.6, cy)], fill=c)


def _lock(d, cx, cy, r, c, w):
    # qulf (tana + qavs)
    bw, bh = r * 1.3, r * 1.0
    d.rounded_rectangle([cx - bw / 2, cy - bh * 0.1, cx + bw / 2, cy + bh], 5, fill=c)
    d.arc([cx - bw * 0.32, cy - bh * 0.95, cx + bw * 0.32, cy + bh * 0.25], 180, 360,
          fill=c, width=w)


def _check(d, cx, cy, r, c, w):
    d.line([(cx - r * 0.7, cy), (cx - r * 0.1, cy + r * 0.6), (cx + r * 0.8, cy - r * 0.6)],
           fill=c, width=w + 1, joint="curve")


def _calendar(d, cx, cy, r, c, w):
    d.rounded_rectangle([cx - r, cy - r * 0.8, cx + r, cy + r], 6, outline=c, width=w)
    d.line([(cx - r, cy - r * 0.25), (cx + r, cy - r * 0.25)], fill=c, width=w)
    d.line([(cx - r * 0.5, cy - r), (cx - r * 0.5, cy - r * 0.55)], fill=c, width=w)
    d.line([(cx + r * 0.5, cy - r), (cx + r * 0.5, cy - r * 0.55)], fill=c, width=w)


def _bulb(d, cx, cy, r, c, w):
    d.ellipse([cx - r * 0.75, cy - r, cx + r * 0.75, cy + r * 0.5], outline=c, width=w)
    d.line([(cx - r * 0.35, cy + r * 0.55), (cx + r * 0.35, cy + r * 0.55)], fill=c, width=w)
    d.line([(cx - r * 0.25, cy + r * 0.85), (cx + r * 0.25, cy + r * 0.85)], fill=c, width=w)


def _trophy(d, cx, cy, r, c, w):
    d.rounded_rectangle([cx - r * 0.7, cy - r, cx + r * 0.7, cy + r * 0.2], 6, outline=c, width=w)
    d.arc([cx - r * 1.2, cy - r * 0.9, cx - r * 0.4, cy + r * 0.1], 90, 270, fill=c, width=w)
    d.arc([cx + r * 0.4, cy - r * 0.9, cx + r * 1.2, cy + r * 0.1], 270, 90, fill=c, width=w)
    d.line([(cx, cy + r * 0.2), (cx, cy + r * 0.6)], fill=c, width=w)
    d.line([(cx - r * 0.5, cy + r), (cx + r * 0.5, cy + r)], fill=c, width=w + 1)


def _return(d, cx, cy, r, c, w):
    # vazvrat (aylanma o'q)
    d.arc([cx - r, cy - r, cx + r, cy + r], 40, 300, fill=c, width=w)
    d.polygon([(cx + r * 0.75, cy - r * 0.5), (cx + r * 1.05, cy - r * 0.1),
               (cx + r * 0.5, cy - r * 0.05)], fill=c)


_MAP = {
    "target": _target, "sales": _sales, "kpi": _kpi, "debt": _debt,
    "growth": _growth, "flag": _flag, "lock": _lock, "check": _check,
    "calendar": _calendar, "bulb": _bulb, "trophy": _trophy, "return": _return,
}
