"""Fail-safe economic-event context for automated paper decisions.

Trading Economics is optional and requires the user's own API key.  The
service never invents events: it uses a short local cache when the provider is
temporarily unavailable and reports an explicit unavailable state otherwise.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from core.market_session import IST


HIGH_IMPACT_TERMS = (
    "interest rate", "monetary policy", "rbi", "federal reserve", "fed", "fomc",
    "cpi", "inflation", "gdp", "employment", "non farm", "payroll", "budget",
    "election", "unemployment", "industrial production",
)


def _parse_datetime(value):
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(IST)


class EconomicCalendarService:
    def __init__(self, api_key="", cache_path=None, timeout=12):
        self.api_key = str(api_key or "").strip()
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant" / "cache"
        self.cache_path = Path(cache_path) if cache_path else base / "economic_calendar.json"
        self.timeout = timeout

    def _normalize(self, rows):
        events = []
        for row in rows or []:
            name = str(row.get("Event") or row.get("event") or row.get("Category") or "Economic event").strip()
            country = str(row.get("Country") or row.get("country") or "").strip()
            event_time = _parse_datetime(row.get("Date") or row.get("date") or row.get("datetime"))
            importance = int(float(row.get("Importance") or row.get("importance") or 0))
            if not event_time:
                continue
            keyword_high = any(term in f"{name} {country}".lower() for term in HIGH_IMPACT_TERMS)
            if importance < 2 and not keyword_high:
                continue
            events.append({
                "name": name, "country": country, "time": event_time.isoformat(),
                "importance": max(importance, 3 if keyword_high else importance),
                "actual": row.get("Actual"), "forecast": row.get("Forecast"), "previous": row.get("Previous"),
                "source": "Trading Economics",
            })
        return sorted(events, key=lambda item: item["time"])

    def fetch(self, now=None):
        now = now or datetime.now(IST)
        now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        if not self.api_key:
            return self._cached_or_unavailable("Economic-calendar API key is not configured")
        start = (now - timedelta(days=1)).date().isoformat()
        end = (now + timedelta(days=1)).date().isoformat()
        countries = quote("india,united states")
        url = f"https://api.tradingeconomics.com/calendar/country/{countries}/{start}/{end}?c={quote(self.api_key)}"
        try:
            request = Request(url, headers={"User-Agent": "TPS-AI-Trading-Assistant/1.1"})
            with urlopen(request, timeout=self.timeout) as response:
                rows = json.loads(response.read().decode("utf-8"))
            events = self._normalize(rows)
            payload = {"fetched_at": now.isoformat(), "events": events}
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return {**payload, "available": True, "cached": False, "error": None}
        except Exception as error:
            return self._cached_or_unavailable(f"Economic calendar unavailable: {error}")

    def _cached_or_unavailable(self, message):
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched = _parse_datetime(payload.get("fetched_at"))
            if fetched and datetime.now(IST) - fetched <= timedelta(hours=24):
                return {**payload, "available": True, "cached": True, "error": message}
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass
        return {"available": False, "cached": False, "events": [], "error": message, "fetched_at": None}

    def assess(self, now=None, window_minutes=30):
        now = now or datetime.now(IST)
        now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        feed = self.fetch(now)
        window = timedelta(minutes=int(window_minutes))
        nearby = []
        for event in feed["events"]:
            event_time = _parse_datetime(event.get("time"))
            if event_time and abs(event_time - now) <= window:
                minutes = round((event_time - now).total_seconds() / 60)
                nearby.append({**event, "minutes_from_now": minutes})
        high = [event for event in nearby if int(event.get("importance", 0)) >= 3]
        return {
            **feed, "nearby_events": nearby, "high_impact_events": high,
            "blocked": bool(high), "risk_multiplier": .5 if high else .8 if nearby else 1.0,
            "confidence_penalty": 20 if high else 10 if nearby else 0,
            "status": "HIGH-IMPACT EVENT WINDOW" if high else "EVENT CAUTION" if nearby else "CLEAR" if feed["available"] else "FEED UNAVAILABLE",
        }
