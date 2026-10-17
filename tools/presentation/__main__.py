"""
Ishlatish (loyiha ildizidan):

  ./venv/bin/python -m tools.presentation build --start 2026-11-01 --end 2026-11-15 \\
        --region shahar --slug noyabr-2026 --from-server

  --from-server   server bazasining nusxasini FAQAT O'QIB oladi (railway ssh, mode=ro) — eng yangi ma'lumot
  --db PATH       tayyor bot.db nusxasidan o'qish
  --region        shahar | viloyat
  --slug          natija: webadmin/presentations/<slug>.html  (mavjud faylni --force'siz bosib yozmaydi)
  --out PATH      boshqa joyga yozish (masalan sinov uchun)
  --overrides F   qo'lda matnlar (xulosa kartalari / yakuniy matn) — README'ga qarang
  --prognoz-days  calendar | 26 ...  (standart: config.yaml)
  --label         muqovadagi yorliq (standart: 1-YARIM OY / OY YAKUNI)
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SNAP = ("python3 -c \"import sqlite3,sys,base64;s=sqlite3.connect('file:/app/data/bot.db?mode=ro',uri=True);"
        "m=sqlite3.connect(':memory:');s.backup(m);sys.stdout.write(base64.b64encode(m.serialize()).decode())\"")


def snapshot_from_server() -> Path:
    """Server bazasining nusxasi — faqat o'qish (serverga hech narsa yozilmaydi)."""
    out = subprocess.run(["railway", "ssh", "--", SNAP], cwd=ROOT, capture_output=True, text=True, check=True)
    data = base64.b64decode("".join(out.stdout.split()))
    d = Path(tempfile.mkdtemp(prefix="pres-db-"))
    (d / "bot.db").write_bytes(data)
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.presentation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--start", required=True, type=date.fromisoformat)
    b.add_argument("--end", required=True, type=date.fromisoformat)
    b.add_argument("--region", choices=["shahar", "viloyat"], default="shahar")
    b.add_argument("--slug")
    b.add_argument("--out")
    b.add_argument("--force", action="store_true")
    src = b.add_mutually_exclusive_group(required=True)
    src.add_argument("--db")
    src.add_argument("--from-server", action="store_true")
    b.add_argument("--overrides")
    b.add_argument("--prognoz-days")
    b.add_argument("--label")
    a = ap.parse_args(argv)

    if a.end < a.start or a.start.month != a.end.month:
        ap.error("--start va --end bir oy ichida bo'lsin, start ≤ end")
    out = Path(a.out) if a.out else (ROOT / "webadmin" / "presentations" / f"{a.slug}.html" if a.slug else None)
    if out is None:
        ap.error("--slug yoki --out kerak")
    if out.exists() and not a.force:
        ap.error(f"{out} allaqachon bor — ustidan yozish uchun --force (tasdiqlangan sahifalarni ehtiyot qiling)")

    data_dir = snapshot_from_server() if a.from_server else Path(a.db).resolve().parent
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ.setdefault("NAZORAT_BOT_TOKEN", "presentation")
    sys.path.insert(0, str(ROOT))

    import yaml

    from tools.presentation import compute, render
    ov = yaml.safe_load(Path(a.overrides).read_text(encoding="utf-8")) if a.overrides else None
    pd = a.prognoz_days if a.prognoz_days in (None, "calendar") else int(a.prognoz_days)
    model = compute.compute(a.start, a.end, a.region, prognoz_days=pd, label=a.label, overrides=ov)
    out.write_text(render.render(model), encoding="utf-8")
    print(f"✓ {out}  ({out.stat().st_size // 1024} KB, ma'lumot: {data_dir}/bot.db)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
