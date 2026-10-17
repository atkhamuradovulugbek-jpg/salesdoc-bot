"""
fromhtml.py — tayyor prezentatsiya HTML'idan MODELni qayta o'qiydi (render'ning teskarisi).

Ishlatilishi: (1) testda render(fromhtml(oktyabr)) == oktyabr — dizayn aynan saqlanganini isbotlash;
(2) validatsiyada hisoblangan raqamlarni eski sahifadagilar bilan katakma-katak solishtirish.
"""

from __future__ import annotations

import html
import re

from lxml import html as LH


def _t(el) -> str:
    return el.text_content() if el is not None else ""


def _color(el) -> str:
    m = re.search(r"\bc-([wmagry])\b", el.get("class", ""))
    return m.group(1) if m else "w"


def _cells(tr, namecols):
    out = []
    for ci, td in enumerate(tr.findall("td")):
        cls = td.get("class", "")
        if "name" in cls.split():
            b, sm = td.find(".//b"), td.find(".//small")
            t = _t(b) + ("\n" + _t(sm) if sm is not None else "")
            namecols.add(ci)
            out.append({"t": t, "c": _color(td)})
        elif td.find(".//span[@class]") is not None and "rank" in td.find(".//span[@class]").get("class", ""):
            out.append({"t": _t(td.find(".//span")), "c": "w", "_medal": True})
        elif "txt" in cls.split():
            # <br> → \n
            for br in td.iter("br"):
                br.tail = "\n" + (br.tail or "")
            out.append({"t": td.text_content(), "c": _color(td), "_text": True})
        else:
            v = td.find(".//span[@class='v']")
            hc = td.find(".//span[@class='hc']")
            el = v if v is not None else hc
            out.append({"t": _t(el) if el is not None else "", "c": _color(td), "_heat": hc is not None})
    return out


def _bars(tr):
    res = {}
    for ci, td in enumerate(tr.findall("td")):
        bar = td.find(".//span[@class]")
        for sp in td.iter("span"):
            if "bar" in sp.get("class", "").split():
                i = sp.find("i")
                em = sp.find("em")
                w = float(re.search(r"--w:([\d.]+)%", i.get("style")).group(1))
                mk = float(re.search(r"left:([\d.]+)%", em.get("style")).group(1)) if em is not None else None
                res[ci] = (w, mk)
    return res


def parse(src: str) -> dict:
    doc = LH.fromstring(src)
    secs = doc.xpath("//section")
    m = {"title": doc.findtext(".//title")}
    c = secs[0]
    m["cover"] = {
        "topbar": _t(c.find(".//div[@class='topbar rv']/span")),
        "l1": _t(c.xpath(".//span[contains(@class,'l1')]")[0]),
        "l2": _t(c.xpath(".//span[contains(@class,'l2')]")[0]),
        "src": [s.strip("\n") for s in html.unescape(
            re.search(r'<p class="src[^>]*>(.*?)</p>', src, re.S).group(1)).split("<br>")],
        "kpis": [(_t(k.find("span")), _t(k.find("b"))) for k in c.xpath(".//div[contains(@class,'kpi ')]")],
    }
    tables = []
    for s in secs[1:]:
        tbl = s.find(".//table")
        if tbl is None:
            continue
        cols = [float(re.search(r"width:([\d.]+)%", col.get("style")).group(1)) for col in tbl.iter("col")]
        heads = []
        for th in tbl.iter("th"):
            for br in th.iter("br"):
                br.tail = "\n" + (br.tail or "")
            heads.append(th.text_content())
        body_rows, total, namecols, textcols, toprows, alerts = [], None, set(), set(), 0, set()
        medal, heat, barinfo = None, False, {}
        for ri, tr in enumerate(tbl.find("tbody").findall("tr")):
            cls = tr.get("class", "").split()
            cells = _cells(tr, namecols)
            for ci, x in enumerate(cells):
                if x.pop("_medal", False):
                    medal = ci
                if x.pop("_text", False):
                    textcols.add(ci)
                if x.pop("_heat", False):
                    heat = True
            if "tot" in cls:
                total = cells
                continue
            if "top" in cls:
                toprows = max(toprows, ri + 1)
            if "alert" in cls:
                alerts.add(ri)
            for ci, (w, mk) in _bars(tr).items():
                barinfo.setdefault(ci, []).append((cells[ci]["t"], w, mk))
            body_rows.append(cells)
        bars = {}
        for ci, lst in barinfo.items():
            # max = qiymat / (w/100); belgi = mk% * max / 100
            for t, w, mk in lst:
                v = float(re.sub(r"[^\d.]", "", t) or 0)
                if 0 < w < 100 and v:
                    mx = round(v / (w / 100))
                    break
            else:
                mx = max(float(re.sub(r"[^\d.]", "", t) or 0) for t, _, _ in lst)
            mark = next((mk for _, _, mk in lst if mk is not None), None)
            bars[ci] = (mx, round(mark * mx / 100) if mark is not None else None)
        note = s.xpath(".//p[contains(@class,'note')]")
        tables.append({
            "sec": _t(s.xpath(".//div[contains(@class,'sec ')]")[0]),
            "title": _t(s.find(".//h2")), "sub": _t(s.xpath(".//p[contains(@class,'sub')]")[0]),
            "cols": cols, "head": heads, "rows": body_rows, "total": total,
            "note": _t(note[0]) if note else "",
            "namecols": namecols or {0}, "textcols": textcols, "toprows": toprows,
            "medalcol": medal, "heat": heat, "bars": bars, "alerts": alerts,
        })
    m["tables"] = tables
    xs = [s for s in secs if s.find(".//div[@class='cards']") is not None][0]
    icons_by_src = {}
    cards = []
    for art in xs.xpath(".//article"):
        tone = re.search(r"tone-(\w)", art.get("class")).group(1)
        cards.append([_t(art.find(".//h3")), _t(art.find(".//p")), None, tone])
    m["xulosa"] = {"sec": _t(xs.xpath(".//div[contains(@class,'sec ')]")[0]), "title": _t(xs.find(".//h2")),
                   "sub": _t(xs.xpath(".//p[contains(@class,'sub')]")[0]),
                   "cards": [tuple(c[:2] + [ic] + c[3:]) for c, ic in zip(cards, ["bag", "gift", "star", "store"])]}
    f = secs[-1]
    m["final"] = {"big": _t(f.find(".//h2")), "f2": _t(f.xpath(".//p[contains(@class,'f2')]")[0]),
                  "f3": _t(f.xpath(".//p[contains(@class,'f3')]")[0])}
    return m
