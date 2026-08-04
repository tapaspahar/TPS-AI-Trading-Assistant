"""Objective TPS Entry Confirmation System v2 rules for auto paper validation."""
from __future__ import annotations

from engine.live_setup_capture import ema, supertrend


def evaluate_tps_entry_v2(candles, capture, chain=None):
    """Evaluate six chart confirmations plus hard chop and option-chain filters."""
    close = float(capture["close"])
    ema_5, ema_20, ema_50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    vwap = float(capture["vwap"]) if capture.get("vwap") else None
    trend_line = float(capture["supertrend"])
    atr = float(capture["atr_14"]) if capture.get("atr_14") else max(close * 0.001, 1)
    volume_ratio = float(capture["volume_ratio"]) if capture.get("volume_ratio") else 0
    bullish = close > trend_line
    direction, candidate = ("BULLISH", "CE") if bullish else ("BEARISH", "PE")

    confirmations = []

    def add(name, passed, detail):
        confirmations.append({"name": name, "passed": bool(passed), "detail": detail})

    vwap_ok = vwap is not None and ((bullish and close > vwap) or (not bullish and close < vwap))
    add("Price vs VWAP", vwap_ok, f"Close {close:.2f} {'>' if bullish else '<'} VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable")
    ema_ok = ema_5 > ema_20 > ema_50 if bullish else ema_5 < ema_20 < ema_50
    add("EMA 5/20/50 alignment", ema_ok, f"EMA5 {ema_5:.2f}, EMA20 {ema_20:.2f}, EMA50 {ema_50:.2f}")
    add("SuperTrend confirmation", True, f"Close {close:.2f} is on the {direction.lower()} side of SuperTrend {trend_line:.2f}")

    tolerance = max(atr * 0.35, close * 0.0005)
    zones = [ema_5, ema_20] + ([vwap] if vwap is not None else [])
    prior = candles[-5:-1]
    if bullish:
        pullback = any(any(abs(float(candle["low"]) - zone) <= tolerance for zone in zones) for candle in prior) and float(capture["close"]) > float(capture["open"])
    else:
        pullback = any(any(abs(float(candle["high"]) - zone) <= tolerance for zone in zones) for candle in prior) and float(capture["close"]) < float(capture["open"])
    add("Pullback and reversal", pullback, f"Recent EMA/VWAP touch within {tolerance:.2f} points followed by a {capture.get('candle_direction', 'neutral').lower()} candle")

    strong_volume = volume_ratio >= 1.5 and capture.get("candle_direction") == direction and not capture.get("fake_breakout_risk", True)
    add("Directional volume", strong_volume, f"{volume_ratio:.2f}x Volume EMA 20; candle {capture.get('candle_direction', 'NEUTRAL')}")

    chain = chain or {}
    level = chain.get("call_resistance") if bullish else chain.get("put_support")
    if level is None:
        level = capture.get("opening_range_high") if bullish else capture.get("opening_range_low")
    level = float(level) if level not in (None, "") else None
    required_room = max(atr * 0.75, close * 0.001)
    if level is None:
        level_ok, level_detail = False, "Support/resistance level unavailable"
    elif bullish:
        room = level - close
        level_ok = close > level or room >= required_room
        level_detail = f"Call resistance {level:.2f}; {'breakout confirmed' if close > level else f'room {room:.2f} points'}"
    else:
        room = close - level
        level_ok = close < level or room >= required_room
        level_detail = f"Put support {level:.2f}; {'breakdown confirmed' if close < level else f'room {room:.2f} points'}"
    add("Breakout/support-resistance safety", level_ok, level_detail)

    blockers = []
    compression_limit = max(atr * 0.10, close * 0.0003)
    if abs(ema_5 - ema_20) <= compression_limit:
        blockers.append(f"EMA5 and EMA20 are compressed ({abs(ema_5 - ema_20):.2f} <= {compression_limit:.2f})")
    recent_closes = [float(item["close"]) for item in candles[-6:]]
    if vwap is not None:
        crossings = sum((recent_closes[i] - vwap) * (recent_closes[i - 1] - vwap) < 0 for i in range(1, len(recent_closes)))
        if crossings >= 2 and abs(close - vwap) <= atr * 0.5:
            blockers.append(f"VWAP chop detected ({crossings} crossings in recent candles)")
    closes = [float(item["close"]) for item in candles]
    prior_ema_50 = ema(closes[:-3], 50) if len(closes) > 53 else ema_50
    if abs(ema_50 - prior_ema_50) <= max(atr * 0.05, close * 0.0001):
        blockers.append("EMA50 is flat; trend strength is insufficient")
    states = []
    for end in range(max(11, len(candles) - 6), len(candles) + 1):
        window = candles[:end]
        states.append(float(window[-1]["close"]) >= supertrend(window[-60:]))
    changes = sum(states[index] != states[index - 1] for index in range(1, len(states)))
    if changes >= 2:
        blockers.append(f"SuperTrend whipsaw detected ({changes} recent direction changes)")
    if not strong_volume:
        blockers.append("Strong directional volume confirmation is missing")
    if capture.get("fake_breakout_risk", True):
        blockers.append("Rejection-wick / fake-breakout risk is active")

    pcr_oi = chain.get("pcr_oi")
    pcr_volume = chain.get("pcr_volume")
    chain_ok = pcr_oi is not None and not ((bullish and pcr_oi < 0.75) or (not bullish and pcr_oi > 1.25))
    if pcr_oi is None:
        blockers.append("Option-chain OI/PCR confirmation is unavailable")
    elif not chain_ok:
        blockers.append(f"OI PCR {pcr_oi:.2f} conflicts with the {candidate} direction")

    passed = sum(item["passed"] for item in confirmations)
    ready = passed >= 5 and not blockers and chain_ok
    return {
        "version": "TPS Entry Confirmation System v2", "direction": direction, "candidate": candidate,
        "confirmations": confirmations, "passed": passed, "required": 5, "total": 6,
        "score": round(passed / 6 * 100), "trade_ready": ready,
        "decision": f"TPS V2 {candidate} ENTRY CONFIRMED" if ready else "NO TRADE",
        "blockers": blockers, "pcr_oi": pcr_oi, "pcr_volume": pcr_volume,
    }
