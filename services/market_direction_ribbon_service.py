"""Compact, evidence-timed direction snapshot for the persistent ticker ribbon."""

from __future__ import annotations

from datetime import datetime

from core.market_session import IST, market_session
from engine.index_component_breadth import combine_market_evidence


INDEXES = ("NIFTY", "BANKNIFTY", "SENSEX")


def build_market_direction_ribbon(database, now=None) -> dict:
    now = now.astimezone(IST) if now and now.tzinfo else now.replace(tzinfo=IST) if now else datetime.now(IST)
    trade_date = now.strftime("%d-%m-%Y")
    breadth = []
    candles = []
    for symbol in INDEXES:
        row = database.get_latest_index_component_breadth(symbol, trade_date)
        if row:
            breadth.append(dict(row))
    seen = set()
    for row in database.get_index_candle_analyses(trade_date):
        symbol = str(row["symbol"] or "").upper()
        if symbol in INDEXES and symbol not in seen:
            candles.append(dict(row))
            seen.add(symbol)
    combined = combine_market_evidence(breadth, candles)
    by_symbol = {str(row.get("symbol") or "").upper(): row for row in combined.get("indexes") or []}
    parts = []
    latest = "-"
    for symbol in INDEXES:
        item = by_symbol.get(symbol) or {}
        direction = str(item.get("direction") or "DATA GAP").upper()
        no_evidence = int(item.get("evidence_votes") or 0) == 0
        display = "DATA GAP" if no_evidence else "FLAT" if direction in {"MIXED", "MIXED / UNCONFIRMED", "NEUTRAL"} else direction
        if display not in {"BULLISH", "BEARISH", "FLAT"}:
            display = "DATA GAP"
        stamp = str(item.get("last_evidence_at") or item.get("candle_time") or item.get("captured_at") or "")
        if stamp:
            latest = max(latest, stamp)
        parts.append({"symbol": symbol, "direction": display})
    overall = str(combined.get("direction") or "DATA GAP").upper()
    if overall in {"MIXED", "MIXED / UNCONFIRMED", "NEUTRAL"}:
        overall = "FLAT"
    if overall not in {"BULLISH", "BEARISH", "FLAT"}:
        votes = [item["direction"] for item in parts if item["direction"] in {"BULLISH", "BEARISH"}]
        overall = (
            "DATA GAP" if all(item["direction"] == "DATA GAP" for item in parts)
            else "BULLISH" if votes.count("BULLISH") >= 2
            else "BEARISH" if votes.count("BEARISH") >= 2 else "FLAT"
        )
    try:
        evidence_time = datetime.fromisoformat(latest).strftime("%H:%M")
    except (TypeError, ValueError):
        evidence_time = "--:--"
    return {
        "overall": overall, "indexes": parts, "evidence_time": evidence_time,
        "session": market_session(now)["state"],
    }
