"""
start_all.py — Railway'da uchala jarayonni bitta konteynerda ishga tushiradi:
  1. bot.py            — asosiy salesdoc-bot (adminlar monitoringi)
  2. nazorat.run       — Siribom Nazorat bot (agentlar motivatsiyasi)
  3. webadmin.main     — admin web dastur (FAQAT O'QIYDI, PIN bilan)

Uchalasi bitta bot.db'ni ulashadi (WAL + busy_timeout). Har biri alohida
jarayon; biri yiqilsa qayta ishga tushadi, boshqalariga xalaqit bermaydi.
Web dastur bazaga hech narsa yozmaydi — botlarni buzmaydi.
"""

import os
import subprocess
import sys
import time

# Railway ochiq port beradi (domen ulangach). Bo'lmasa 8000.
_PORT = os.getenv("PORT", "8000")

PROCS = [
    ("asosiy-bot", [sys.executable, "bot.py"]),
    ("nazorat-bot", [sys.executable, "-m", "nazorat.run"]),
    ("web", [sys.executable, "-m", "uvicorn", "webadmin.main:app",
             "--host", "0.0.0.0", "--port", _PORT, "--workers", "1"]),
]

RESTART_DELAY = 10  # sekund


def main():
    running: dict[str, subprocess.Popen] = {}
    for name, cmd in PROCS:
        print(f"[launcher] {name} ishga tushmoqda: {' '.join(cmd)}", flush=True)
        running[name] = subprocess.Popen(cmd)

    try:
        while True:
            time.sleep(5)
            for name, cmd in PROCS:
                p = running[name]
                code = p.poll()
                if code is not None:
                    print(f"[launcher] ⚠️ {name} to'xtadi (kod {code}), "
                          f"{RESTART_DELAY}s dan keyin qayta ishga tushadi", flush=True)
                    time.sleep(RESTART_DELAY)
                    running[name] = subprocess.Popen(cmd)
    except KeyboardInterrupt:
        for p in running.values():
            p.terminate()


if __name__ == "__main__":
    main()
