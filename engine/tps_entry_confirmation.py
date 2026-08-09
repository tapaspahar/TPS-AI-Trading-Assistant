"""TPS three-layer CE/PE evaluator specified in the 05-08 Notion postmortem.

Direction is an output, never a prerequisite.  Analytical evidence is scored
independently from execution blockers so a mixed market can still expose a
stronger CE or PE watch candidate without silently authorising a trade.
"""
from __future__ import annotations

from engine.live_setup_capture import ema, supertrend
from engine.market_structure import analyze_candles


CONDITION_WEIGHTS = {
    "Market structure": 16,
    "Price vs VWAP": 16,
    "EMA 5/20/50 alignment": 16,
    "SuperTrend confirmation": 18,
    "Pullback and reversal": 12,
    "Directional volume": 12,
    "OI/PCR context": 10,
    "Market environment / VIX": 10,
}
DEFAULT_ENABLED = tuple(CONDITION_WEIGHTS)


def _side_condition(name, passed, detail):
    return {"name": name, "passed": bool(passed), "detail": detail}


def _side_score(confirmations, enabled):
    selected = [item for item in confirmations if item["name"] in enabled]
    possible = sum(CONDITION_WEIGHTS[item["name"]] for item in selected)
    earned = sum(CONDITION_WEIGHTS[item["name"]] for item in selected if item["passed"])
    return round(earned / possible * 100) if possible else 0, selected


def evaluate_tps_entry_v2(candles, capture, chain=None, settings=None, environment=None):
    """Return independent CE/PE evidence, checklist result and hard blockers."""
    chain, settings = chain or {}, settings or {}
    enabled = [name for name in settings.get("tps_enabled_conditions", DEFAULT_ENABLED) if name in CONDITION_WEIGHTS]
    if not enabled:
        enabled = list(DEFAULT_ENABLED)
    match_mode = settings.get("tps_match_mode", "count")
    required = len(enabled) if match_mode == "all" else max(1, min(int(settings.get("tps_required_matches", 5)), len(enabled)))
    minimum_score = max(0, min(int(settings.get("trade_plan_min_score", 95)), 100))

    close = float(capture["close"]); opening = float(capture["open"])
    ema_5, ema_20, ema_50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    vwap = float(capture["vwap"]) if capture.get("vwap") else None
    trend_line = float(capture["supertrend"])
    atr = float(capture["atr_14"]) if capture.get("atr_14") else max(close * .001, 1)
    rsi = float(capture["rsi_14"]) if capture.get("rsi_14") else None
    volume_ratio = float(capture["volume_ratio"]) if capture.get("volume_ratio") else 0
    candle_direction = capture.get("candle_direction", "NEUTRAL")
    structure = analyze_candles(candles)
    structure_state = structure["state"]
    chart_support, chart_resistance = float(structure["support"]), float(structure["resistance"])
    oi_support = float(chain["put_support"]) if chain.get("put_support") not in (None, "") else None
    oi_resistance = float(chain["call_resistance"]) if chain.get("call_resistance") not in (None, "") else None
    pcr_oi, pcr_volume = chain.get("pcr_oi"), chain.get("pcr_volume")
    pcr_oi = float(pcr_oi) if pcr_oi is not None else None
    pcr_volume = float(pcr_volume) if pcr_volume is not None else None
    tolerance = max(atr * .35, close * .0005)
    zones = [ema_5, ema_20] + ([vwap] if vwap is not None else [])
    prior = candles[-5:-1]
    recent_bullish_touch = any(any(abs(float(c["low"]) - zone) <= tolerance for zone in zones) for c in prior)
    recent_bearish_touch = any(any(abs(float(c["high"]) - zone) <= tolerance for zone in zones) for c in prior)
    environment = environment or {}
    environment_ok = not environment or (
        float(environment.get("risk_multiplier", 1)) >= .75 and environment.get("vix_zone") != "EXTREME RISK"
    )
    environment_detail = (
        f"{environment.get('regime', 'unavailable')}; VIX {environment.get('vix_zone', 'unavailable')}; "
        f"risk multiplier {environment.get('risk_multiplier', 1)}"
    )
    volume_threshold = float(environment.get("volume_threshold", 1.5))
    strong_quality = volume_ratio >= volume_threshold and not capture.get("fake_breakout_risk", True)

    common = {
        "CE": [
            _side_condition("Market structure", structure_state.startswith("Bullish"), structure_state),
            _side_condition("Price vs VWAP", vwap is not None and close > vwap, f"Close {close:.2f} > VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable"),
            _side_condition("EMA 5/20/50 alignment", ema_5 > ema_20 > ema_50, f"EMA5 {ema_5:.2f} > EMA20 {ema_20:.2f} > EMA50 {ema_50:.2f}"),
            _side_condition("SuperTrend confirmation", close > trend_line, f"Close {close:.2f} > SuperTrend {trend_line:.2f}"),
            _side_condition("Pullback and reversal", recent_bullish_touch and close > opening, f"EMA/VWAP touch within {tolerance:.2f}; candle {candle_direction}"),
            _side_condition("Directional volume", strong_quality and candle_direction == "BULLISH", f"{volume_ratio:.2f}x Volume EMA20; required {volume_threshold:.2f}x; candle {candle_direction}"),
            _side_condition("OI/PCR context", pcr_oi is not None and pcr_volume is not None and pcr_oi >= .75 and pcr_volume <= 1.25, f"OI PCR {pcr_oi if pcr_oi is not None else '-'}; Volume PCR {pcr_volume if pcr_volume is not None else '-'}"),
            _side_condition("Market environment / VIX", environment_ok, environment_detail),
        ],
        "PE": [
            _side_condition("Market structure", structure_state.startswith("Bearish"), structure_state),
            _side_condition("Price vs VWAP", vwap is not None and close < vwap, f"Close {close:.2f} < VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable"),
            _side_condition("EMA 5/20/50 alignment", ema_5 < ema_20 < ema_50, f"EMA5 {ema_5:.2f} < EMA20 {ema_20:.2f} < EMA50 {ema_50:.2f}"),
            _side_condition("SuperTrend confirmation", close < trend_line, f"Close {close:.2f} < SuperTrend {trend_line:.2f}"),
            _side_condition("Pullback and reversal", recent_bearish_touch and close < opening, f"EMA/VWAP touch within {tolerance:.2f}; candle {candle_direction}"),
            _side_condition("Directional volume", strong_quality and candle_direction == "BEARISH", f"{volume_ratio:.2f}x Volume EMA20; required {volume_threshold:.2f}x; candle {candle_direction}"),
            _side_condition("OI/PCR context", pcr_oi is not None and pcr_volume is not None and pcr_oi <= 1.25 and pcr_volume >= .80, f"OI PCR {pcr_oi if pcr_oi is not None else '-'}; Volume PCR {pcr_volume if pcr_volume is not None else '-'}"),
            _side_condition("Market environment / VIX", environment_ok, environment_detail),
        ],
    }

    zone_tolerance = max(atr * 2.5, close * .0025)
    support_gap = abs(chart_support - oi_support) if oi_support is not None else None
    resistance_gap = abs(chart_resistance - oi_resistance) if oi_resistance is not None else None
    support_confluence = support_gap is not None and support_gap <= zone_tolerance
    resistance_confluence = resistance_gap is not None and resistance_gap <= zone_tolerance
    required_room = max(atr * .75, close * .001)
    side_results = {}
    for side in ("CE", "PE"):
        score, selected = _side_score(common[side], enabled)
        passed = sum(item["passed"] for item in selected)
        blockers = []
        if capture.get("fake_breakout_risk", True):
            blockers.append("Rejection-wick / fake-breakout risk is active")
        if side == "CE":
            resistance_levels = [level for level in (chart_resistance, oi_resistance) if level is not None]
            nearest = min(resistance_levels) if resistance_levels else None
            room = nearest - close if nearest is not None else None
            breakout = resistance_levels and close > max(resistance_levels)
            if nearest is None:
                blockers.append("Resistance level is unavailable")
            elif 0 <= room < required_room and not breakout:
                blockers.append(f"CE entry is too close to resistance ({room:.2f} < {required_room:.2f} points room)")
            if rsi is not None and rsi >= 70 and not breakout:
                blockers.append(f"RSI {rsi:.1f} is overbought near resistance")
        else:
            support_levels = [level for level in (chart_support, oi_support) if level is not None]
            nearest = max(support_levels) if support_levels else None
            room = close - nearest if nearest is not None else None
            breakdown = support_levels and close < min(support_levels)
            if nearest is None:
                blockers.append("Support level is unavailable")
            elif 0 <= room < required_room and not breakdown:
                blockers.append(f"PE entry is too close to support ({room:.2f} < {required_room:.2f} points room)")
            if rsi is not None and rsi <= 30 and not breakdown:
                blockers.append(f"RSI {rsi:.1f} is oversold near support")
        checklist_matched = passed >= required
        score_matched = score >= minimum_score
        ready = checklist_matched and score_matched and not blockers
        side_results[side] = {
            "candidate": side, "confirmations": common[side], "selected_confirmations": selected,
            "passed": passed, "total": len(selected), "required": required, "score": score,
            "checklist_matched": checklist_matched, "score_matched": score_matched,
            "hard_blockers": blockers, "trade_ready": ready,
            "state": "EXECUTE" if ready else "REJECTED" if blockers else "WATCH",
        }

    ce, pe = side_results["CE"], side_results["PE"]
    valid = [side for side in (ce, pe) if side["trade_ready"]]
    if len(valid) == 1:
        selected = valid[0]; direction = "BULLISH" if selected["candidate"] == "CE" else "BEARISH"
    elif len(valid) == 2:
        selected = max(valid, key=lambda item: item["score"]); direction = "CONFLICT / HEDGE WATCH"
        selected = {**selected, "trade_ready": False, "hard_blockers": selected["hard_blockers"] + ["Both CE and PE passed; conflict requires hedge/manual review"]}
    else:
        selected = max((ce, pe), key=lambda item: (item["score"], item["passed"]))
        direction = "BULLISH WATCH" if selected["candidate"] == "CE" else "BEARISH WATCH" if selected["candidate"] == "PE" else "MIXED"

    return {
        "version": "TPS Entry Confirmation System v3 - independent CE/PE",
        "direction": direction, "candidate": selected["candidate"], "side_evaluations": side_results,
        "confirmations": selected["confirmations"], "selected_confirmations": selected["selected_confirmations"],
        "passed": selected["passed"], "required": required, "total": selected["total"], "score": selected["score"],
        "minimum_score": minimum_score, "enabled_conditions": enabled,
        "trade_ready": bool(selected["trade_ready"]),
        "decision": f"TPS V3 {selected['candidate']} PAPER ENTRY CONFIRMED" if selected["trade_ready"] else f"{selected['candidate']} {selected['state']}",
        "blockers": selected["hard_blockers"], "hard_blockers": selected["hard_blockers"],
        "pcr_oi": pcr_oi, "pcr_volume": pcr_volume, "structure_state": structure_state,
        "market_environment": environment,
        "zones": {"chart_support": chart_support, "chart_resistance": chart_resistance,
                  "oi_support": oi_support, "oi_resistance": oi_resistance,
                  "support_gap": support_gap, "resistance_gap": resistance_gap,
                  "tolerance": zone_tolerance, "support_confluence": support_confluence,
                  "resistance_confluence": resistance_confluence},
    }
