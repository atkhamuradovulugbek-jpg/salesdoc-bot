"""
render.py — prezentatsiya MODELi → mustaqil HTML (oktyabr-2026 dizayni, animatsiyalari, logo 4-variant).

Asos: Cowork sessiyasidagi gen.py (2026-10-17) — u pptx'dan o'qirdi; bu yerda bevosita model
qabul qilinadi, shuning uchun har oy uchun pptx kerak emas. Belgilanishi (class'lar, --d kechikishlar,
data-c sanovchilar) gen.py bilan bir xil — CSS/JS (template/) o'zgarishsiz ishlaydi.

MODEL (dict):
  title: str                                   — <title>
  cover: {topbar, l1, l2, src: [qator, ...], kpis: [(yorliq, qiymat) × 3]}
  tables: [6 ta jadval-slayd]  har biri:
      {sec, title, sub, cols: [nisbiy kengliklar], head: [ustun nomi ('\\n' = yangi qator)],
       rows: [[cell, ...], ...], total: [cell, ...] | None, note,
       namecols: {i}, textcols: {i}, toprows: n, medalcol: i | None, heat: bool,
       bars: {ustun: (max, belgi | None)}, alerts: {qator_indeksi (0 dan)}}
      cell = {"t": matn, "c": rang}  rang: w oq · m kulrang · a binafsha · g yashil · r qizil · y sariq
  xulosa: {sec, title, sub, cards: [(sarlavha, matn, ikonka bag|gift|star|store, ton g|y|r)] × 4}
  final:  {big, f2, f3}
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"
e = html.escape
NUMRE = re.compile(r"^[~+\-]?\d[\d .]*%?( / \d+)?$")


def _b64(name: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode((TEMPLATE / name).read_bytes()).decode()


def _is_num(t: str) -> bool:
    return bool(NUMRE.match(t.strip()))


def cell(t, c="w") -> dict:
    return {"t": "" if t is None else str(t), "c": c}


def render_table(t: dict) -> str:
    cols, head = t["cols"], t["head"]
    tot = sum(cols)
    namecols = t.get("namecols", {0})
    textcols = t.get("textcols", set())
    bars = t.get("bars", {})
    medals = t.get("medalcol")
    toprows = t.get("toprows", 0)
    heat = t.get("heat", False)
    alerts = t.get("alerts", set())
    h = ['<div class="tscroll"><table class="dt" style="--n:%d">' % len(cols), "<colgroup>"]
    for w in cols:
        h.append(f'<col style="width:{w / tot * 100:.2f}%">')
    h.append("</colgroup><thead><tr>")
    for i, c in enumerate(head):
        al = "l" if i in namecols or i in textcols else "c"
        h.append(f'<th class="{al}">' + e(c).replace("\n", "<br>") + "</th>")
    h.append("</tr></thead><tbody>")
    rows = list(t["rows"]) + ([t["total"]] if t.get("total") else [])
    for ri, row in enumerate(rows, 1):
        is_total = t.get("total") is not None and ri == len(rows)
        cls = ["rv"]
        if is_total:
            cls.append("tot")
        elif ri <= toprows:
            cls.append(f"top top{ri}")
        if not is_total and (ri - 1) in alerts:
            cls.append("alert")
        h.append(f'<tr class="{" ".join(cls)}" style="--d:{ri * 70}">')
        for ci, c in enumerate(row):
            text, col = c["t"], c.get("c", "w")
            if ci in namecols:
                parts = text.split("\n")
                inner = f'<b class="nm">{e(parts[0])}</b>'
                if len(parts) > 1:
                    inner += f"<small>{e(parts[1])}</small>"
                h.append(f'<td class="l name c-{col}">{inner}</td>')
                continue
            if medals is not None and ci == medals and not is_total and text.strip():
                n = int(text)
                mc = f" md{n}" if n <= 3 else ""
                h.append(f'<td class="c"><span class="rank{mc}">{e(text)}</span></td>')
                continue
            if ci in textcols:
                h.append(f'<td class="l txt c-{col}">{e(text).replace(chr(10), "<br>")}</td>')
                continue
            tcls = ["c", f"c-{col}"]
            if heat and text.strip() and ci > 0:
                tcls.append(f"h-{col}")
                inner = f'<span class="hc" data-c>{e(text)}</span>'
                h.append(f'<td class="{" ".join(tcls)}" style="--hd:{ci * 90 + ri * 35}">{inner}</td>')
                continue
            inner = f'<span class="v"{" data-c" if _is_num(text) else ""}>{e(text)}</span>' if text else ""
            if ci in bars and not is_total and text.strip():
                mx, mark = bars[ci]
                v = float(re.sub(r"[^\d.]", "", text) or 0)
                w = min(v / mx * 100, 100) if mx else 0
                mk = f'<em style="left:{mark / mx * 100:.1f}%"></em>' if mark else ""
                inner += f'<span class="bar b-{col}">{mk}<i style="--w:{w:.1f}%"></i></span>'
            h.append(f'<td class="{" ".join(tcls)}">{inner}</td>')
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def _head(sec, title, sub) -> str:
    return f'''<div class="sec rv" style="--d:0">{e(sec)}</div>
<header class="ttl"><h2 class="rv" style="--d:60">{e(title)}</h2>
<p class="sub rv" style="--d:160">{e(sub)}</p></header>'''


def render(model: dict) -> str:
    slides = []
    cv = model["cover"]
    k = cv["kpis"]
    slides.append(f'''<section class="slide hero" data-i="1"><div class="stage">
<div class="topbar rv" style="--d:0"><span>{e(cv["topbar"])}</span></div>
<div class="cover">
  <h1><span class="l1 rv" style="--d:150">{e(cv["l1"])}</span><span class="l2 rv grad" style="--d:330">{e(cv["l2"])}</span></h1>
  <p class="src rv" style="--d:600">{"<br>".join(e(x) for x in cv["src"])}</p>
  <div class="kpis">
    <div class="kpi rv" style="--d:850"><span>{e(k[0][0])}</span><b data-c>{e(k[0][1])}</b></div>
    <div class="kpi rv glow" style="--d:1000"><span>{e(k[1][0])}</span><b data-c>{e(k[1][1])}</b></div>
    <div class="kpi rv" style="--d:1150"><span>{e(k[2][0])}</span><b data-c>{e(k[2][1])}</b></div>
  </div>
</div></div></section>''')
    for i, t in enumerate(model["tables"], 2):
        slides.append(f'''<section class="slide content t{i}" data-i="{i}"><div class="stage">
{_head(t["sec"], t["title"], t["sub"])}
<div class="panel rv" style="--d:250">{render_table(t)}</div>
<p class="note rv" style="--d:900">{e(t["note"])}</p>
</div></section>''')
    xu = model["xulosa"]
    n = len(model["tables"]) + 2
    ch = []
    for j, (h3, p, ic, tone) in enumerate(xu["cards"]):
        ch.append(f'''<article class="card rv tone-{tone}" style="--d:{300 + j * 180}">
<div class="ic"><img src="{_b64(f"ic_{ic}.png", "image/png")}" alt=""></div>
<div><h3>{e(h3)}</h3><p>{e(p)}</p></div></article>''')
    slides.append(f'''<section class="slide content t{n}" data-i="{n}"><div class="stage">
{_head(xu["sec"], xu["title"], xu["sub"])}
<div class="cards">{"".join(ch)}</div>
</div></section>''')
    fi = model["final"]
    slides.append(f'''<section class="slide hero final" data-i="{n + 1}"><div class="stage">
<div class="fin">
<h2 class="rv" style="--d:150"><span data-c class="big17">{e(fi["big"])}</span></h2>
<p class="f2 rv" style="--d:650">{e(fi["f2"])}</p>
<p class="f3 rv" style="--d:1050">{e(fi["f3"])}</p>
</div></div></section>''')
    css = (TEMPLATE / "style.css").read_text(encoding="utf-8").replace("__BG__", _b64("bg.jpg", "image/jpeg"))
    js = (TEMPLATE / "app.js").read_text(encoding="utf-8")
    return f'''<!DOCTYPE html>
<html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(model["title"])}</title>
<style>{css}</style></head>
<body>
<div id="deck">
{"".join(slides)}
</div>
<img class="logo" src="{_b64("logo.png", "image/png")}" alt="Siribom">
<div class="hud">
  <button id="prev" aria-label="Oldingi">&#8249;</button>
  <span id="cnt">1 / {n + 1}</span>
  <button id="next" aria-label="Keyingi">&#8250;</button>
  <button id="fs" aria-label="To'liq ekran" title="To'liq ekran (F)">&#x26F6;</button>
</div>
<div class="prog"><i id="bar"></i></div>
<div class="hint" id="hint">→ / Space — keyingi slayd • F — to'liq ekran</div>
<script>{js}</script>
</body></html>'''
