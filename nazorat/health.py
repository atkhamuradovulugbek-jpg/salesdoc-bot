"""
health.py — hisobot YETKAZILISHINI kuzatish (FAIL-LOUD, 0-bosqich).

MUAMMO (2026-07-18): kechki job bitta ketgan agent ustida qulab tushdi va
admin/supervayzer/GPS hisobotlari JIMGINA yuborilmadi. Bot hech narsa demadi —
foydalanuvchi o'zi sezdi. "Noto'g'ri-lekin-yuborilgan kecha" va "yuborilmagan
kecha" bir xil ko'rinardi.

YECHIM (llm-council 5/5 maslahatchi tavsiyasi):
  1. Har bir yuborish ALOHIDA himoyalanadi — biri yiqilsa qolgani baribir ketadi.
  2. Natija nz_job_run jadvaliga yoziladi (qaysi blok, necha ok/xato, qaysi xato).
  3. Watchdog (kechki 20:40 / ertalabki 10:30) adminga BITTA xabar yuboradi:
     nima ketdi, nima ketmadi, job tugadimi.

Bu modul Telegram'ga bog'liq EMAS — sof mantiq, testlanadi.
"""

from __future__ import annotations

import json

# Yuborish natijalari
SENT = "sent"          # yuborildi
DUP = "dup"            # allaqachon yuborilgan (idempotent o'tkazish)
UNBOUND = "unbound"    # agent botga ulanmagan — yuborilmaydi (xato emas)
SKIP = "skip"          # kerak bo'lmadi (masalan: 0-ball signali shart emas)
FAIL = "fail"          # XATO — yuborilmadi
_ALL = (SENT, DUP, UNBOUND, SKIP, FAIL)

BLOCK_LABELS = {
    "dc": "Ma'lumot tayyorlash",
    "agent": "Agent kartalari",
    "guruh": "Guruh reyting",
    "admin": "Admin svodka",
    "supervayzer": "Supervayzer jadvallari",
    "gps": "GPS xulosa",
    "signal": "0-ball ogohlantirish",
    "super-qarz": "Supervayzer qarz-vazvrat",
    "yangi-agent": "Yangi agent xabari",
    "qarz-snapshot": "Qarz tarixi saqlash",
}

JOB_LABELS = {"evening": "KECHKI", "morning": "ERTALABKI"}
MAX_ERRORS = 8


class RunReport:
    """Bitta job yurishining natijasi: blok bo'yicha ok/xato/o'tkazilgan + xatolar."""

    def __init__(self, job: str, day: str):
        self.job = job
        self.day = day
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.last_block: str = ""
        self.blocks: dict[str, dict] = {}

    # ---- yozish ----

    def start(self, now: str) -> None:
        self.started_at = now

    def note(self, block: str, status: str, who: str = "", err: object = None) -> None:
        b = self.blocks.setdefault(
            block, {s: 0 for s in _ALL} | {"errors": [], "who_unbound": []})
        if status not in _ALL:
            status = SENT
        b[status] += 1
        self.last_block = block
        if status == FAIL:
            if len(b["errors"]) < MAX_ERRORS:
                msg = f"{type(err).__name__}: {err}" if err is not None else "noma'lum xato"
                b["errors"].append({"who": who, "err": msg[:200]})
        elif status == UNBOUND and who and len(b["who_unbound"]) < MAX_ERRORS:
            b["who_unbound"].append(who)

    def finish(self, now: str) -> None:
        self.finished_at = now

    # ---- saqlash / o'qish ----

    def payload(self) -> str:
        return json.dumps({"last_block": self.last_block, "blocks": self.blocks},
                          ensure_ascii=False)

    def totals(self) -> dict:
        t = {s: 0 for s in _ALL}
        for b in self.blocks.values():
            for k in t:
                t[k] += b.get(k, 0)
        return t

    def short(self) -> str:
        t = self.totals()
        return (f"yuborildi={t[SENT]} o'tkazildi={t[DUP]} ulanmagan={t[UNBOUND]} "
                f"XATO={t[FAIL]}")

    @property
    def failed(self) -> bool:
        return self.totals()[FAIL] > 0


# ------------------------------------------------------------------
# Watchdog xabari (nz_job_run qatoridan matn quradi)
# ------------------------------------------------------------------

RUNNING_OK_MIN = 40      # shu vaqt ichida tugamagan job "hali ishlayapti" deb hisoblanadi


def build_watchdog_text(job: str, day_label: str, row: dict | None,
                        running_age_min: float | None = None) -> str:
    """
    row: {"started_at","finished_at","payload"} yoki None (umuman ishlamagan).
    Qaytadi: adminga yuboriladigan tayyor matn.
    """
    jl = JOB_LABELS.get(job, job.upper())

    if row is None or not row.get("started_at"):
        return (f"🚨 {jl} HISOBOT UMUMAN ISHLAMADI! · {day_label}\n\n"
                f"Bugun hech narsa yuborilmagan. Bot yoki jadval ishlamayapti.\n\n"
                f"Menga (Claude) shu xabarni ko'rsating — tekshiraman.")

    try:
        data = json.loads(row.get("payload") or "{}")
    except (ValueError, TypeError):
        data = {}
    blocks: dict = data.get("blocks") or {}
    last_block = data.get("last_block") or ""

    lines: list[str] = []
    total_fail = 0
    unbound_names: list[str] = []

    for key, label in BLOCK_LABELS.items():
        b = blocks.get(key)
        if not b:
            continue
        sent, fail = b.get(SENT, 0), b.get(FAIL, 0)
        dup, unb, skip = b.get(DUP, 0), b.get(UNBOUND, 0), b.get(SKIP, 0)
        total_fail += fail
        unbound_names.extend(b.get("who_unbound") or [])

        total = sent + fail + dup           # mo'ljallangan yuborishlar
        if fail:
            lines.append(f"❌ {label} — {sent}/{total} ({fail} XATO)")
            for e in (b.get("errors") or []):
                who = f"{e.get('who')}: " if e.get("who") else ""
                lines.append(f"     • {who}{e.get('err')}")
        elif sent:
            extra = f" (+{dup} avval yuborilgan)" if dup else ""
            lines.append(f"✅ {label} — {sent}/{total}{extra}")
        elif dup:
            lines.append(f"✅ {label} — {dup} ta avval yuborilgan")
        elif skip:
            lines.append(f"ℹ️ {label} — kerak bo'lmadi")
        elif unb:
            lines.append(f"ℹ️ {label} — ulanmagan {unb} ta")

    if not row.get("finished_at") and running_age_min is not None \
            and running_age_min < RUNNING_OK_MIN:
        # Hali ishlayapti (sync band bo'lib kechikkan bo'lishi mumkin) — trevoga emas.
        head = (f"⏳ {jl} HISOBOT HALI DAVOM ETYAPTI · {day_label}\n\n"
                f"{row['started_at'][11:19]} da boshlandi ({running_age_min:.0f} daqiqa oldin).\n"
                f"Hozirgi bosqich: {BLOCK_LABELS.get(last_block, last_block or '?')}\n")
    elif not row.get("finished_at"):
        head = (f"🚨 {jl} HISOBOT TUGAMADI! · {day_label}\n\n"
                f"{row['started_at'][11:19]} da boshlandi, TUGAMADI.\n"
                f"Oxirgi bosqich: {BLOCK_LABELS.get(last_block, last_block or '?')}\n"
                f"Undan keyingi hisobotlar yuborilmagan.\n")
    elif total_fail:
        head = f"🚨 {jl} HISOBOTDA MUAMMO · {day_label}\n"
    else:
        head = f"🌙 {jl} HISOBOT NAZORATI · {day_label}\n"

    out = [head]
    out.extend(lines or ["(hech qanday yuborish qayd etilmagan)"])

    if unbound_names:
        uniq = sorted(set(unbound_names))
        out.append(f"\nUlanmagan: {len(uniq)} ta ({', '.join(uniq[:6])}"
                   f"{' …' if len(uniq) > 6 else ''})")

    still_running = (not row.get("finished_at") and running_age_min is not None
                     and running_age_min < RUNNING_OK_MIN)
    if still_running:
        out.append("\nTugagach yana tekshiriladi.")
    elif not row.get("finished_at") or total_fail:
        out.append("\n⚠️ Menga (Claude) shu xabarni ko'rsating — tekshiraman.")
    else:
        out.append("\nHammasi joyida ✅")

    return "\n".join(out)
