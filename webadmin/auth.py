"""
auth.py — web dastur kirish himoyasi (0.5-bosqich). SOF MANTIQ (FastAPI'siz, testlanadi).

NEGA (llm-council, 5/5 tekshiruvchi topdi): 1-bosqichda web faqat O'QIRDI — 6 raqamli PIN
yetardi. 2-bosqichda web PUL raqamlarini (ball plan, sovrin, promo) o'zgartiradi — ochiq
havolada 6 raqam 18 kishining bonusini boshqaradi. Shuning uchun:
  1. Uzun parol (WEB_PASSWORD), PIN emas.
  2. Token MUDDATI bor (30 kun) — imzolangan, serverda holat saqlanmaydi.
  3. Noto'g'ri kiritishga CHEKLOV (5 marta xato → 15 daqiqa blok) — brute-force himoyasi.

Ko'chirish (foydalanuvchi qulflanib qolmasligi uchun): WEB_PASSWORD qo'yilmagan bo'lsa,
eski WEB_PIN ishlaydi, lekin dastur "himoya kuchsiz" deb ogohlantiradi. WEB_PASSWORD
qo'yilgach — faqat u ishlaydi, PIN o'chadi.
"""

from __future__ import annotations

import hashlib
import hmac
import time

TOKEN_DAYS = 30          # token muddati
MAX_FAILS = 5            # shuncha xatodan keyin blok boshlanadi
BLOCK_SECONDS = 60       # 1-blok: 1 daqiqa (egasi o'zini qulflab qo'ymasligi uchun)
BLOCK_MAX = 15 * 60      # eng uzun blok: 15 daqiqa (qaytariladigan urinishlarda)
MIN_STRONG_LEN = 8       # shundan qisqa = kuchsiz (ogohlantiriladi)


# ------------------------------------------------------------------
# Token: "<muddat>.<imzo>" — serverda hech narsa saqlanmaydi
# ------------------------------------------------------------------

def _sign(secret: str, exp: int) -> str:
    return hmac.new(secret.encode(), f"nz:{exp}".encode(), hashlib.sha256).hexdigest()


def make_token(secret: str, days: int = TOKEN_DAYS, now: float | None = None) -> str:
    exp = int((now if now is not None else time.time()) + days * 86400)
    return f"{exp}.{_sign(secret, exp)}"


def token_valid(secret: str, token: str, now: float | None = None) -> bool:
    if not secret or not token:
        return False
    exp_s, _, sig = token.partition(".")
    if not exp_s.isdigit() or not sig:
        return False
    if int(exp_s) <= (now if now is not None else time.time()):
        return False                                  # muddati o'tgan
    return hmac.compare_digest(sig, _sign(secret, int(exp_s)))


def password_ok(secret: str, given: str) -> bool:
    """Doimiy vaqtli solishtirish (timing attack'ga qarshi)."""
    if not secret or not given:
        return False
    return hmac.compare_digest(secret, given)


def is_weak(secret: str) -> bool:
    """Faqat eski PIN ishlatilyaptimi (qisqa/raqamli) — UI ogohlantiradi."""
    return bool(secret) and (len(secret) < MIN_STRONG_LEN or secret.isdigit())


# ------------------------------------------------------------------
# Brute-force cheklovi (xotirada; jarayon qayta ishga tushsa tozalanadi)
# ------------------------------------------------------------------

class RateLimiter:
    """Progressiv blok: har 5 xatodan keyin blok, har safar 2 barobar (1→2→4→8→15 daq).

    NEGA progressiv (2026-07-30 tuzatildi): oldin 1-blok ham 15 daqiqa edi va egasi
    (bitta foydalanuvchi) o'zini qulflab qo'yardi — eski keshlangan sahifa parolni
    qirqib yuborgani uchun. 1 daqiqa brute-force'ni baribir imkonsiz qiladi
    (daqiqada 5 urinish), lekin egasini kutdirib qo'ymaydi.
    """

    def __init__(self, max_fails: int = MAX_FAILS, block_seconds: int = BLOCK_SECONDS,
                 block_max: int = BLOCK_MAX):
        self.max_fails = max_fails
        self.block_seconds = block_seconds
        self.block_max = block_max
        self._state: dict[str, tuple[int, float]] = {}   # kalit -> (xato soni, blok tugashi)

    def _block_len(self, fails: int) -> int:
        """5 xato → 1 daq, 10 → 2 daq, 15 → 4 daq … (block_max gacha)."""
        step = fails // self.max_fails - 1          # 0, 1, 2, ...
        return min(self.block_seconds * (2 ** max(step, 0)), self.block_max)

    def blocked_for(self, key: str, now: float | None = None) -> int:
        """Qancha soniya blok qolgani (0 = blok yo'q)."""
        now = now if now is not None else time.time()
        _, until = self._state.get(key, (0, 0.0))
        return int(until - now) + 1 if until > now else 0

    def fail(self, key: str, now: float | None = None) -> int:
        """Noto'g'ri urinish. Qaytadi: blok soniyalari (0 = hali blok emas)."""
        now = now if now is not None else time.time()
        fails, until = self._state.get(key, (0, 0.0))
        if until > now:
            return int(until - now) + 1
        fails += 1
        until = now + self._block_len(fails) if fails % self.max_fails == 0 else 0.0
        self._state[key] = (fails, until)
        return int(until - now) + 1 if until > now else 0

    def reset(self, key: str) -> None:
        self._state.pop(key, None)
