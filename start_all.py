"""
start_all.py — Railway'da ikkala botni bitta konteynerda ishga tushiradi:
  1. bot.py            — asosiy salesdoc-bot (adminlar monitoringi)
  2. nazorat.run       — Siribom Nazorat bot (agentlar motivatsiyasi)

Ikkalasi bitta bot.db'ni ulashadi (WAL + busy_timeout). Har biri alohida
jarayon; biri yiqilsa qayta ishga tushadi, ikkinchisiga xalaqit bermaydi.
"""

import subprocess
import sys
import time

PROCS = [
    ("asosiy-bot", [sys.executable, "bot.py"]),
    ("nazorat-bot", [sys.executable, "-m", "nazorat.run"]),
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
