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
    maximum_favourable = maximum_adverse = 0.0
    for candle in candles[index + 1:index + 1 + max_bars]:
        high, low = float(candle["high"]), float(candle["low"])
        if direction == "BULLISH":
            maximum_favourable = max(maximum_favourable, high - entry)
            maximum_adverse = max(maximum_adverse, entry - low)
            if low <= stop:
                return "STOP LOSS", stop, maximum_favourable, maximum_adverse
            if high >= target:
                return "TARGET", target, maximum_favourable, maximum_adverse
        else:
            maximum_favourable = max(maximum_favourable, entry - low)
            maximum_adverse = max(maximum_adverse, high - entry)
            if high >= stop:
                return "STOP LOSS", stop, maximum_favourable, maximum_adverse
            if low <= target:
                return "TARGET", target, maximum_favourable, maximum_adverse
    future = candles[min(index + max_bars, len(candles) - 1)]
    return "TIME EXIT", float(future["close"]), maximum_favourable, maximum_adverse


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
        outcome = exit_price = None
        hypothetical_outcome = hypothetical_exit = None
        hypothetical_mfe = hypothetical_mae = 0.0
        candidate_direction = "BULLISH" if strategy.get("candidate") == "CE" else "BEARISH"
        hypothetical_outcome, hypothetical_exit, hypothetical_mfe, hypothetical_mae = _paper_outcome(
            candles, index, candidate_direction, float(capture["close"]), float(capture["atr_14"])
        )
        hypothetical_entry = float(capture["close"])
        hypothetical_risk = max(float(capture["atr_14"]), hypothetical_entry * .002)
        hypothetical_stop = hypothetical_entry - hypothetical_risk if candidate_direction == "BULLISH" else hypothetical_entry + hypothetical_risk
        hypothetical_target = hypothetical_entry + hypothetical_risk * 2 if candidate_direction == "BULLISH" else hypothetical_entry - hypothetical_risk * 2
        if strategy["trade_ready"]:
            outcome, exit_price, _mfe, _mae = _paper_outcome(
                candles, index, strategy["direction"], float(capture["close"]), float(capture["atr_14"])
            )
        evaluations.append({
            "time": str(candles[index]["time"]), "capture": capture, "strategy": strategy,
            "oi_available": snapshot is not None, "outcome": outcome, "exit_price": exit_price,
            "hypothetical_outcome": hypothetical_outcome, "hypothetical_exit": hypothetical_exit,
            "hypothetical_mfe": round(hypothetical_mfe, 2), "hypothetical_mae": round(hypothetical_mae, 2),
            "hypothetical_entry": round(hypothetical_entry, 2), "hypothetical_stop": round(hypothetical_stop, 2),
            "hypothetical_target": round(hypothetical_target, 2),
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
    rejected = [row for row in audit["evaluations"] if not row["strategy"]["trade_ready"]]
    rejected_winners = sum(row["hypothetical_outcome"] == "TARGET" for row in rejected)
    rejected_losers = sum(row["hypothetical_outcome"] == "STOP LOSS" for row in rejected)
    lines.append(f"Rejected outcome audit: hypothetical targets {rejected_winners} | hypothetical stops {rejected_losers}")
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
                f"{strategy['passed']}/{strategy.get('total', 7)} | OI {'matched' if row['oi_available'] else 'unavailable'} | "
                f"Hypothetical {row['hypothetical_outcome']} | Entry {row['hypothetical_entry']:.2f} | "
                f"SL {row['hypothetical_stop']:.2f} | Target {row['hypothetical_target']:.2f} | "
                f"MFE {row['hypothetical_mfe']:.2f}, MAE {row['hypothetical_mae']:.2f} | {blockers}"
            )
    lines.append("Outcome uses underlying-future candles, a conservative stop-first rule, and excludes option premium/slippage/taxes.")
    return "\n".join(lines)
