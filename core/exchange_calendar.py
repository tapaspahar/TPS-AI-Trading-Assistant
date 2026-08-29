"""NSE equity/F&O trading-day calendar with an official-source fallback.

The bundled dates come from the NSE F&O holiday circular for 2026.  A small
AppData JSON cache may supplement later years without changing user settings.
Unknown future years remain weekday-only instead of inventing holidays.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path


NSE_HOLIDAY_SOURCE = "https://www.nseindia.com/resources/exchange-communication-holidays"
NSE_2026_FO_CIRCULAR = "https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf"

OFFICIAL_TRADING_HOLIDAYS = {
    2026: {
        date(2026, 1, 26): "Republic Day",
        date(2026, 3, 3): "Holi",
        date(2026, 3, 26): "Shri Ram Navami",
        date(2026, 3, 31): "Shri Mahavir Jayanti",
        date(2026, 4, 3): "Good Friday",
        date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
        date(2026, 5, 1): "Maharashtra Day",
        date(2026, 5, 28): "Bakri Id",
        date(2026, 6, 26): "Muharram",
        date(2026, 9, 14): "Ganesh Chaturthi",
        date(2026, 10, 2): "Mahatma Gandhi Jayanti",
        date(2026, 10, 20): "Dussehra",
        date(2026, 11, 10): "Diwali-Balipratipada",
        date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
        date(2026, 12, 25): "Christmas",
    }
}


def _cache_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache" / "nse_trading_holidays.json"


def _cached_holidays():
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("holidays", payload) if isinstance(payload, dict) else payload
        result = {}
        for row in rows if isinstance(rows, list) else []:
            day = datetime.strptime(str(row.get("date")), "%Y-%m-%d").date()
            result[day] = str(row.get("description") or row.get("name") or "NSE trading holiday")
        return result
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def trading_holiday(day):
    """Return the official/cached holiday name, or ``None`` for a trading day."""
    if isinstance(day, datetime):
        day = day.date()
    return OFFICIAL_TRADING_HOLIDAYS.get(day.year, {}).get(day) or _cached_holidays().get(day)


def next_trading_day(day):
    candidate = day + timedelta(days=1)
    while candidate.weekday() >= 5 or trading_holiday(candidate):
        candidate += timedelta(days=1)
    return candidate
