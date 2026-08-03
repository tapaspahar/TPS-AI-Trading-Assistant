"""Explainable long-only equity planning from historical OHLCV candles."""
from __future__ import annotations

from engine.live_setup_capture import build_live_capture
from engine.market_structure import analyze_candles


def analyze_equity(candles):
    """Build a research plan. It never submits an order or promises an outcome."""
    if len(candles) < 51:
        raise ValueError("At least 51 candles are needed for equity analysis.")
    capture = build_live_capture("EQUITY", "1D", candles, "Angel One NSE equity candle data")
    structure = analyze_candles(candles)
    price = float(capture["close"])
    atr = float(capture["atr_14"])
    rsi = float(capture["rsi_14"])
    bullish = structure["state"] == "Bullish structure"
    volume_ok = not capture["fake_breakout_risk"]
    score = 35 + (25 if bullish else 0) + (15 if price > float(capture["ema_20"]) else 0) + (15 if 50 <= rsi <= 70 else 0) + (10 if volume_ok else 0)
    entry = float(structure["breakout_level"])
    stop_loss = round(max(min(float(structure["support"]) - atr * 0.20, entry - atr), entry * 0.50), 2)
    risk = max(entry - stop_loss, atr * 0.5)
    target_1, target_2 = entry + risk, entry + risk * 2
    if bullish and score >= 70:
        plan_state, plan_note = "WATCH LONG BREAKOUT", "Consider only after a close above entry with volume confirmation."
    elif bullish:
        plan_state, plan_note = "WATCHLIST - CONFIRMATION NEEDED", "Trend is constructive, but wait for stronger volume or momentum confirmation."
    else:
        plan_state, plan_note = "NO LONG TRADE - WAIT", "Daily structure is not bullish. Reassess after structure improves."
    return {"price": price, "state": structure["state"], "support": structure["support"], "resistance": structure["resistance"], "entry": entry, "stop_loss": stop_loss, "target_1": target_1, "target_2": target_2, "rsi_14": rsi, "atr_14": atr, "volume_signal": capture["volume_signal"], "score": min(score, 100), "plan_state": plan_state, "plan_note": plan_note, "candle_count": len(candles)}
