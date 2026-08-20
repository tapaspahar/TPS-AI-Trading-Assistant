"""Persistent trend-memory generation and live historical analog checks."""

from __future__ import annotations

import json
from datetime import datetime, time

from core.database_manager import Database
from engine.trend_memory_engine import build_daily_fingerprint, find_best_analogs

MIN_COMPLETED_SESSION_SNAPSHOTS = 24
MIN_LIVE_ANALOG_SNAPSHOTS = 12


def _date(value: str):
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported trade date: {value}")


def _record(row) -> dict:
    item = dict(row)
    try:
        item["features"] = json.loads(item.get("features_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        item["features"] = {}
    return item


def ensure_completed_trend_memories(database: Database, now: datetime | None = None) -> list[dict]:
    """Finalize every completed trading date with saved 5-minute observations."""
    current = now or datetime.now()
    updated = []
    existing = {(r["trade_date"], r["symbol"]): int(r["snapshot_count"]) for r in database.get_daily_trend_memories(limit=5000)}
    for source in database.get_market_snapshot_dates():
        trade_date, symbol = str(source["trade_date"]), str(source["symbol"])
        day = _date(trade_date)
        completed = day < current.date() or (day == current.date() and current.time() >= time(15, 31))
        if not completed or int(source["snapshot_count"] or 0) < MIN_COMPLETED_SESSION_SNAPSHOTS:
            continue
        key = (trade_date, symbol)
        if existing.get(key) == int(source["snapshot_count"]):
            continue
        rows = database.get_market_snapshots_for_symbol(trade_date, symbol)
        memory = build_daily_fingerprint(rows, symbol, trade_date)
        memory["generated_at"] = current.isoformat(timespec="seconds")
        database.save_daily_trend_memory(memory)
        updated.append(memory)
    return updated


def get_live_trend_analogs(database: Database, now: datetime | None = None, minimum_snapshots: int = MIN_LIVE_ANALOG_SNAPSHOTS) -> list[dict]:
    """Compare today's developing fingerprint with completed historical days."""
    current = now or datetime.now()
    dates = {current.strftime("%d-%m-%Y"), current.strftime("%Y-%m-%d")}
    historical = [_record(row) for row in database.get_daily_trend_memories(limit=2000)]
    results = []
    for trade_date in dates:
        for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
            rows = database.get_market_snapshots_for_symbol(trade_date, symbol)
            five_minute = [row for row in rows if str(row["timeframe"]).lower() == "5m"]
            if len(five_minute) < minimum_snapshots:
                continue
            fingerprint = build_daily_fingerprint(rows, symbol, trade_date)
            matches = find_best_analogs(fingerprint, historical, limit=3)
            if matches:
                results.append({"current": fingerprint, "matches": matches, "context_only": True,
                                "permission_effect": "NONE — analog similarity never permits or blocks an entry"})
    return results


def load_trend_memory_view(database: Database, symbol: str) -> tuple[list[dict], list[dict]]:
    records = [_record(row) for row in database.get_daily_trend_memories(symbol, limit=500)]
    live = get_live_trend_analogs(database)
    return records, [item for item in live if item["current"]["symbol"] == symbol.upper()]
