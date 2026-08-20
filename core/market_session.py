"""NSE cash-market session countdown using India Standard Time.

Weekend handling is included. Exchange holidays are intentionally shown as normal
weekdays until an official holiday-calendar sync is added.
"""
from datetime import datetime, time, timedelta, timezone


# India does not observe daylight saving time, so a fixed IST offset is reliable
# and avoids depending on a system timezone database.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
PRE_OPEN = time(9, 0)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def _parse_clock(value, fallback, *, strict=False):
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError):
        if strict:
            raise ValueError("Market timings must use 24-hour HH:MM format.")
        return fallback


def parse_session_times(settings=None):
    """Return validated pre-open/open/close times from local preferences."""
    values = settings
    if values is None:
        from core.settings_store import SettingsStore
        values = SettingsStore().load()
    pre_open = _parse_clock(values.get("market_pre_open_time"), PRE_OPEN, strict="market_pre_open_time" in values)
    market_open = _parse_clock(values.get("market_open_time"), MARKET_OPEN, strict="market_open_time" in values)
    market_close = _parse_clock(values.get("market_close_time"), MARKET_CLOSE, strict="market_close_time" in values)
    if not pre_open <= market_open < market_close:
        raise ValueError("Market timings must follow: pre-open start <= trading start < market close.")
    return pre_open, market_open, market_close


def _next_business_day(day):
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def market_session(now=None, settings=None):
    now = now.astimezone(IST) if now and now.tzinfo else now.replace(tzinfo=IST) if now else datetime.now(IST)
    pre_open_at, market_open_at, market_close_at = parse_session_times(settings)
    today = now.date()
    if now.weekday() >= 5:
        opening = datetime.combine(_next_business_day(today), pre_open_at, IST)
        return {"state": "WEEKEND", "deadline": opening, "label": "Weekend — pre-open starts"}
    pre_open = datetime.combine(today, pre_open_at, IST)
    open_time = datetime.combine(today, market_open_at, IST)
    close_time = datetime.combine(today, market_close_at, IST)
    if now < pre_open:
        return {"state": "BEFORE_OPEN", "deadline": pre_open, "label": "Pre-open starts"}
    if now < open_time:
        return {"state": "PRE_OPEN", "deadline": open_time, "label": "Pre-open — regular market opens"}
    if now < close_time:
        return {"state": "OPEN", "deadline": close_time, "label": "Market open — closes"}
    opening = datetime.combine(_next_business_day(today), pre_open_at, IST)
    return {"state": "CLOSED", "deadline": opening, "label": "Market closed — next pre-open"}


def format_remaining(delta):
    seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
