"""Look-ahead-safe TPS v2 audit for one historical trading day."""
from __future__ import annotations

from datetime import datetime, timedelta

from engine.live_setup_capture import build_live_capture
from engine.tps_entry_confirmation import evaluate_tps_entry_v2


def _minute(value):
    return datetime.fromisoformat(str(value)).replace(second=0, microsecond=0, tzinfo=None)


def _paper_outcome(candles, index, direction, entry, atr_value, max_bars=12):
    risk = max(float(atr_value), entry * 0.002)
    stop = entry - risk if direction == "BULLISH" else entry + risk
    target = entry + risk * 2 if direction == "BULLISH" else entry - risk * 2
    for candle in candles[index + 1:index + 1 + max_bars]:
        high, low = float(candle["high"]), float(candle["low"])
        if direction == "BULLISH":
            if low <= stop:
                return "STOP LOSS", stop
            if high >= target:
                return "TARGET", target
        else:
            if high >= stop:
                return "STOP LOSS", stop
            if low <= target:
                return "TARGET", target
    future = candles[min(index + max_bars, len(candles) - 1)]
    return "TIME EXIT", float(future["close"])


def audit_tps_day(candles, snapshots, symbol, trade_date):
    """Replay completed candles using only OI evidence saved at that candle minute."""
    target = datetime.strptime(trade_date, "%d-%m-%Y").date()
    snapshot_by_minute = {
        _minute(row["captured_at"]): row for row in snapshots
        if str(row["symbol"]).upper() == symbol.upper() and row["timeframe"] == "5m"
    }
    evaluations = []
    for index in range(50, len(candles)):
        candle_time = _minute(candles[index]["time"])
        if candle_time.date() != target:
            continue
        # A 09:15 five-minute candle completes at 09:20; use the OI snapshot
        # available at its close, never a later snapshot.
        snapshot = snapshot_by_minute.get(candle_time + timedelta(minutes=5))
        chain = {
            "pcr_oi": snapshot["oi_pcr"] if snapshot else None,
            "pcr_volume": snapshot["volume_pcr"] if snapshot else None,
            "put_support": snapshot["put_support"] if snapshot else None,
            "call_resistance": snapshot["call_resistance"] if snapshot else None,
        }
        history = candles[:index + 1]
        capture = build_live_capture(symbol, "5m", history, "Historical full-day TPS audit")
        capture["candle_time"] = str(candles[index]["time"])
        strategy = evaluate_tps_entry_v2(history, capture, chain)
        outcome = None
        exit_price = None
        if strategy["trade_ready"]:
            outcome, exit_price = _paper_outcome(
                candles, index, strategy["direction"], float(capture["close"]), float(capture["atr_14"])
            )
        evaluations.append({
            "time": str(candles[index]["time"]), "capture": capture, "strategy": strategy,
            "oi_available": snapshot is not None, "outcome": outcome, "exit_price": exit_price,
        })
    setups = [row for row in evaluations if row["strategy"]["trade_ready"]]
    return {
        "trade_date": trade_date, "symbol": symbol, "evaluated": len(evaluations),
        "oi_matched": sum(row["oi_available"] for row in evaluations),
        "setups": setups, "evaluations": evaluations,
    }


def format_tps_day_audit(audit):
    lines = [
        f"Full-day TPS audit: {audit['symbol']} | {audit['trade_date']}",
        f"Completed candles checked: {audit['evaluated']} | OI snapshots matched: {audit['oi_matched']} | Strict setups: {len(audit['setups'])}",
    ]
    if audit["setups"]:
        lines.append("Confirmed historical setups (paper study only):")
        for row in audit["setups"]:
            strategy, capture = row["strategy"], row["capture"]
            lines.append(
                f"{row['time']} | {strategy['candidate']} | Score {strategy['score']}/100 | Entry {capture['close']} | "
                f"Outcome {row['outcome']} at {row['exit_price']:.2f}"
            )
    else:
        ranked = sorted(audit["evaluations"], key=lambda row: row["strategy"]["passed"], reverse=True)[:5]
        lines.append("No strict setup found. Closest completed candles:")
        for row in ranked:
            strategy = row["strategy"]
            blockers = "; ".join(strategy["blockers"][:3]) or "Checklist confirmations were below the minimum"
            lines.append(
                f"{row['time']} | {strategy['direction']} / {strategy['candidate'] or '-'} | "
                f"{strategy['passed']}/6 | OI {'matched' if row['oi_available'] else 'unavailable'} | {blockers}"
            )
    lines.append("Outcome uses underlying-future candles, a conservative stop-first rule, and excludes option premium/slippage/taxes.")
    return "\n".join(lines)
