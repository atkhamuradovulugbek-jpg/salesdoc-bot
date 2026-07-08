"""
workdays.py — ish kunlari (yakshanba dam). Eski bot bilan bir xil mantiq,
etalon iyun 2026 = 26 kun bilan tasdiqlangan.
"""

from datetime import date, timedelta


def month_workdays(year: int, month: int, sunday_off: bool = True) -> list[date]:
    """Oyning barcha ish kunlari ro'yxati."""
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    last = (nxt - timedelta(days=1)).day
    days = []
    for d in range(1, last + 1):
        dt = date(year, month, d)
        if sunday_off and dt.weekday() == 6:
            continue
        days.append(dt)
    return days


def workdays_passed(year: int, month: int, today: date, sunday_off: bool = True) -> int:
    """1-sanadan bugungacha ish kunlari (bugun KIRADI)."""
    return len([d for d in month_workdays(year, month, sunday_off) if d <= today])


def workdays_remaining(year: int, month: int, today: date, sunday_off: bool = True) -> int:
    """Ertangi kundan oy oxirigacha ish kunlari (bugun KIRMAYDI)."""
    return len([d for d in month_workdays(year, month, sunday_off) if d > today])
