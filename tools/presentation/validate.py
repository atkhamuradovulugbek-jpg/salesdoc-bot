"""
validate.py — ikki prezentatsiya HTML'ini katakma-katak solishtiradi (agent ismi bo'yicha).

  ./venv/bin/python -m tools.presentation.validate ESKI.html YANGI.html
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tools.presentation import fromhtml


def _key(row, namecol):
    return row[namecol]["t"].split("\n")[0].replace(" *", "").strip()


def _num(t):
    m = re.sub(r"[^\d.\-]", "", t.replace(" ", ""))
    try:
        return float(m)
    except ValueError:
        return None


def compare(a_src: str, b_src: str) -> dict:
    A, B = fromhtml.parse(a_src), fromhtml.parse(b_src)
    rep = {"cover": [], "tables": []}
    for (ka, va), (kb, vb) in zip(A["cover"]["kpis"], B["cover"]["kpis"]):
        if va != vb:
            rep["cover"].append((ka, va, vb))
    for ta, tb in zip(A["tables"], B["tables"]):
        nc = min(ta["namecols"])
        ia = {_key(r, nc): r for r in ta["rows"]}
        ib = {_key(r, nc): r for r in tb["rows"]}
        t = {"title": ta["title"], "cells": 0, "same": 0, "diffs": [], "only_old": sorted(set(ia) - set(ib)),
             "only_new": sorted(set(ib) - set(ia)), "order_same": [_key(r, nc) for r in ta["rows"]] ==
             [_key(r, nc) for r in tb["rows"]]}
        heads = ta["head"]
        for name in ia.keys() & ib.keys():
            for ci, (x, y) in enumerate(zip(ia[name], ib[name])):
                if ci == nc or (ta.get("medalcol") == ci):
                    continue
                t["cells"] += 1
                if x["t"] == y["t"] and x["c"] == y["c"]:
                    t["same"] += 1
                else:
                    t["diffs"].append((name, heads[ci].replace("\n", " ") if ci < len(heads) else ci,
                                       x["t"], y["t"], x["c"], y["c"]))
        if ta.get("total") and tb.get("total"):
            for ci, (x, y) in enumerate(zip(ta["total"], tb["total"])):
                if x["t"] != y["t"]:
                    t["diffs"].append(("JAMI", heads[ci].replace("\n", " ") if ci < len(heads) else ci, x["t"], y["t"],
                                       "", ""))
        rep["tables"].append(t)
    return rep


def main(argv=None):
    a, b = (argv or sys.argv[1:])[:2]
    rep = compare(Path(a).read_text(encoding="utf-8"), Path(b).read_text(encoding="utf-8"))
    for k, x, y in rep["cover"]:
        print(f"MUQOVA  {k}  {x} → {y}")
    for t in rep["tables"]:
        print(f"\n== {t['title']}: {t['same']}/{t['cells']} katak bir xil; tartib "
              f"{'bir xil' if t['order_same'] else 'FARQ'}")
        if t["only_old"] or t["only_new"]:
            print("   faqat eskida:", t["only_old"], "| faqat yangida:", t["only_new"])
        for name, col, x, y, cx, cy in t["diffs"]:
            nx, ny = _num(x), _num(y)
            d = f"  Δ{ny - nx:+.2f}" if nx is not None and ny is not None else ""
            c = f"  rang {cx}→{cy}" if cx != cy else ""
            print(f"   {name:<11} {col:<24} {x!r:>14} → {y!r:<14}{d}{c}")


if __name__ == "__main__":
    main()
