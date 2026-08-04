"""Objective TPS Entry Confirmation System v2 rules for auto paper validation."""
from __future__ import annotations

from engine.live_setup_capture import ema, supertrend
from engine.market_structure import analyze_candles


def evaluate_tps_entry_v2(candles, capture, chain=None):
    """Evaluate six chart confirmations plus hard chop and option-chain filters."""
    close = float(capture["close"])
    ema_5, ema_20, ema_50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    vwap = float(capture["vwap"]) if capture.get("vwap") else None
    trend_line = float(capture["supertrend"])
    atr = float(capture["atr_14"]) if capture.get("atr_14") else max(close * 0.001, 1)
    volume_ratio = float(capture["volume_ratio"]) if capture.get("volume_ratio") else 0
    structure_state = analyze_candles(candles)["state"]
    votes = {
        "Market structure": "BULLISH" if structure_state.startswith("Bullish") else "BEARISH" if structure_state.startswith("Bearish") else "MIXED",
        "Price vs VWAP": "BULLISH" if vwap is not None and close > vwap else "BEARISH" if vwap is not None and close < vwap else "MIXED",
        "EMA stack": "BULLISH" if ema_5 > ema_20 > ema_50 else "BEARISH" if ema_5 < ema_20 < ema_50 else "MIXED",
        "SuperTrend": "BULLISH" if close > trend_line else "BEARISH",
    }
    bullish_votes = sum(value == "BULLISH" for value in votes.values())
    bearish_votes = sum(value == "BEARISH" for value in votes.values())
    core_votes = (votes["Market structure"], votes["Price vs VWAP"], votes["EMA stack"])
    if all(value == "BULLISH" for value in core_votes):
        direction, candidate = "BULLISH", "CE"
    elif all(value == "BEARISH" for value in core_votes):
        direction, candidate = "BEARISH", "PE"
    else:
        direction, candidate = "MIXED", None
    bullish = direction == "BULLISH"
    bearish = direction == "BEARISH"

    confirmations = []

    def add(name, passed, detail):
        confirmations.append({"name": name, "passed": bool(passed), "detail": detail})

    vwap_ok = vwap is not None and ((bullish and close > vwap) or (bearish and close < vwap))
    comparison = ">" if bullish else "<" if bearish else "vs"
    add("Price vs VWAP", vwap_ok, f"Close {close:.2f} {comparison} VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable")
    ema_ok = (bullish and ema_5 > ema_20 > ema_50) or (bearish and ema_5 < ema_20 < ema_50)
    add("EMA 5/20/50 alignment", ema_ok, f"EMA5 {ema_5:.2f}, EMA20 {ema_20:.2f}, EMA50 {ema_50:.2f}")
    supertrend_ok = (bullish and close > trend_line) or (bearish and close < trend_line)
    add("SuperTrend confirmation", supertrend_ok, f"Close {close:.2f} vs SuperTrend {trend_line:.2f}; selected structure {direction}")

    tolerance = max(atr * 0.35, close * 0.0005)
    zones = [ema_5, ema_20] + ([vwap] if vwap is not None else [])
    prior = candles[-5:-1]
    if bullish:
        pullback = any(any(abs(float(candle["low"]) - zone) <= tolerance for zone in zones) for candle in prior) and float(capture["close"]) > float(capture["open"])
    elif bearish:
        pullback = any(any(abs(float(candle["high"]) - zone) <= tolerance for zone in zones) for candle in prior) and float(capture["close"]) < float(capture["open"])
    else:
        pullback = False
    add("Pullback and reversal", pullback, f"Recent EMA/VWAP touch within {tolerance:.2f} points followed by a {capture.get('candle_direction', 'neutral').lower()} candle")

    strong_volume = volume_ratio >= 1.5 and capture.get("candle_direction") == direction and not capture.get("fake_breakout_risk", True)
    add("Directional volume", strong_volume, f"{volume_ratio:.2f}x Volume EMA 20; candle {capture.get('candle_direction', 'NEUTRAL')}")

    chain = chain or {}
    level = chain.get("call_resistance") if bullish else chain.get("put_support") if bearish else None
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
    elif bearish:
        room = close - level
        level_ok = close < level or room >= required_room
        level_detail = f"Put support {level:.2f}; {'breakdown confirmed' if close < level else f'room {room:.2f} points'}"
    else:
        level_ok, level_detail = False, "Direction is mixed; CE/PE support-resistance test was not selected"
    add("Breakout/support-resistance safety", level_ok, level_detail)

    blockers = []
    if direction == "MIXED":
        blockers.append(
            "Core trend is not fully aligned: Market structure, Price vs VWAP, and EMA stack must all confirm the same direction; "
            f"current votes are {votes}. Neither CE nor PE is permitted"
        )
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
    oi_ok = pcr_oi is not None and ((bullish and pcr_oi >= 0.75) or (bearish and pcr_oi <= 1.25))
    volume_pcr_ok = pcr_volume is not None and ((bullish and pcr_volume <= 1.25) or (bearish and pcr_volume >= 0.80))
    chain_ok = direction != "MIXED" and oi_ok and volume_pcr_ok
    if pcr_oi is None:
        blockers.append("Option-chain OI/PCR confirmation is unavailable")
    elif not oi_ok:
        blockers.append(f"OI PCR {pcr_oi:.2f} conflicts with the {candidate} direction")
    if pcr_volume is None:
        blockers.append("Option-chain Volume PCR confirmation is unavailable")
    elif not volume_pcr_ok:
        blockers.append(f"Volume PCR {pcr_volume:.2f} conflicts with the {candidate} direction")

    passed = sum(item["passed"] for item in confirmations)
    ready = passed >= 5 and not blockers and chain_ok
    return {
        "version": "TPS Entry Confirmation System v2", "direction": direction, "candidate": candidate,
        "confirmations": confirmations, "passed": passed, "required": 5, "total": 6,
        "score": round(passed / 6 * 100), "trade_ready": ready,
        "decision": f"TPS V2 {candidate} ENTRY CONFIRMED" if ready else "NO TRADE",
        "blockers": blockers, "pcr_oi": pcr_oi, "pcr_volume": pcr_volume,
        "structure_state": structure_state, "direction_votes": votes,
    }
