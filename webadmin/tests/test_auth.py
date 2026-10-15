"""Web dastur kirish himoyasi (0.5-bosqich): token muddati, imzo, brute-force cheklovi."""

from webadmin import auth

PW = "juda-uzun-maxfiy-parol-2026"


# ------------------------------------------------------------------
# Parol
# ------------------------------------------------------------------

def test_password_ok_exact_match():
    assert auth.password_ok(PW, PW) is True


def test_password_rejects_wrong_and_empty():
    assert auth.password_ok(PW, "boshqa") is False
    assert auth.password_ok(PW, "") is False
    assert auth.password_ok("", PW) is False          # server sozlanmagan


def test_weak_detects_pin_and_short():
    assert auth.is_weak("123456") is True             # eski PIN
    assert auth.is_weak("0316") is True
    assert auth.is_weak("qisqa") is True              # 8 belgidan kam
    assert auth.is_weak(PW) is False
    assert auth.is_weak("") is False                  # sozlanmagan — "kuchsiz" emas


# ------------------------------------------------------------------
# Token
# ------------------------------------------------------------------

def test_token_valid_right_after_issue():
    t = auth.make_token(PW)
    assert auth.token_valid(PW, t) is True


def test_token_invalid_with_other_password():
    t = auth.make_token(PW)
    assert auth.token_valid("boshqa-parol-butunlay", t) is False


def test_token_expires():
    now = 1_000_000.0
    t = auth.make_token(PW, days=30, now=now)
    assert auth.token_valid(PW, t, now=now + 29 * 86400) is True     # 29-kun: ishlaydi
    assert auth.token_valid(PW, t, now=now + 31 * 86400) is False    # 31-kun: o'tgan


def test_token_signature_cannot_be_forged():
    """Muddatni cho'zib qo'yish imzoni buzadi (parolsiz token yasalmaydi)."""
    now = 1_000_000.0
    t = auth.make_token(PW, days=1, now=now)
    exp, _, sig = t.partition(".")
    forged = f"{int(exp) + 10 * 86400}.{sig}"         # muddat o'zgartirildi
    assert auth.token_valid(PW, forged, now=now) is False


def test_token_garbage_rejected():
    for bad in ("", "abc", "abc.def", ".", "123", "999999999999", "x.y.z"):
        assert auth.token_valid(PW, bad) is False


def test_token_password_change_invalidates_old_tokens():
    old = auth.make_token("eski-parol-uzun-2026")
    assert auth.token_valid(PW, old) is False         # parol o'zgardi → eski token o'chdi


# ------------------------------------------------------------------
# Brute-force cheklovi
# ------------------------------------------------------------------

def test_limiter_blocks_after_max_fails():
    rl = auth.RateLimiter(max_fails=5, block_seconds=60)
    now = 100.0
    for i in range(4):
        assert rl.fail("1.2.3.4", now=now) == 0       # hali blok emas
    blocked = rl.fail("1.2.3.4", now=now)             # 5-xato
    assert blocked > 0
    assert rl.blocked_for("1.2.3.4", now=now) > 0


def test_first_block_is_short_owner_not_locked_out():
    """2026-07-30: 1-blok 15 daqiqa edi va EGASI o'zini qulflab qo'ydi. Endi 1 daqiqa."""
    rl = auth.RateLimiter()
    now = 100.0
    for _ in range(5):
        left = rl.fail("ip", now=now)
    assert 0 < left <= 61                             # ~1 daqiqa
    assert rl.blocked_for("ip", now=now + 62) == 0     # 1 daqiqadan keyin ochiladi


def test_block_doubles_on_repeated_rounds_capped():
    """Qayta-qayta urinsa blok uzayadi (1→2→4 daq), lekin 15 daqiqadan oshmaydi."""
    rl = auth.RateLimiter(max_fails=5, block_seconds=60, block_max=900)
    assert rl._block_len(5) == 60        # 1-tur
    assert rl._block_len(10) == 120      # 2-tur
    assert rl._block_len(15) == 240      # 3-tur
    assert rl._block_len(100) == 900     # eng uzun 15 daqiqa


def test_limiter_unblocks_after_time():
    rl = auth.RateLimiter(max_fails=2, block_seconds=900)
    now = 100.0
    rl.fail("ip", now=now)
    rl.fail("ip", now=now)
    assert rl.blocked_for("ip", now=now) > 0
    assert rl.blocked_for("ip", now=now + 902) == 0    # muddat tugadi


def test_limiter_reset_on_success():
    rl = auth.RateLimiter(max_fails=3)
    rl.fail("ip"); rl.fail("ip")
    rl.reset("ip")
    assert rl.fail("ip") == 0                          # hisob noldan
    assert rl.blocked_for("ip") == 0


def test_limiter_is_per_client():
    rl = auth.RateLimiter(max_fails=2, block_seconds=900)
    now = 100.0
    rl.fail("A", now=now); rl.fail("A", now=now)
    assert rl.blocked_for("A", now=now) > 0
    assert rl.blocked_for("B", now=now) == 0           # boshqa mijoz bloklanmaydi
