"""TPS three-layer CE/PE evaluator specified in the 05-08 Notion postmortem.

Direction is an output, never a prerequisite.  Analytical evidence is scored
independently from execution blockers so a mixed market can still expose a
stronger CE or PE watch candidate without silently authorising a trade.
"""
from __future__ import annotations

from math import ceil

from engine.evidence_model import EvidenceState, evidence_state, unique_messages

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

# Execution-quality safeguards are deliberately independent from the user's
# score threshold.  A low testing score must never turn an exhausted/chased
# candle into an automatic paper entry.
DEFAULT_MAX_ENTRY_EXTENSION_ATR = 0.75
DEFAULT_CE_MAX_RSI = 75.0
DEFAULT_PE_MIN_RSI = 25.0


def _side_condition(name, passed, detail, applicable=True):
    """Build one candle-local checklist result; unavailable evidence is UNKNOWN."""
    return {
        "name": name, "passed": bool(passed) if applicable else False,
        "applicable": bool(applicable),
        "evidence_state": EvidenceState.TRUE.value if applicable and passed else EvidenceState.FALSE.value if applicable else EvidenceState.UNKNOWN.value,
        "status": "PASS" if applicable and passed else "FAIL" if applicable else "UNKNOWN",
        "detail": detail,
    }


def _side_score(confirmations, enabled):
    selected = [item for item in confirmations if item["name"] in enabled and item.get("applicable", True)]
    possible = sum(CONDITION_WEIGHTS[item["name"]] for item in selected)
    earned = sum(CONDITION_WEIGHTS[item["name"]] for item in selected if item["passed"])
    return round(earned / possible * 100) if possible else 0, selected


def _recent_impulse_volume(candles, volume_ema, threshold, side):
    """Accept volume from the impulse immediately preceding a pullback entry.

    Requiring heavy volume on the entry candle itself tends to authorise a
    trade only after price has already expanded.  A directional impulse in the
    previous three completed candles is valid confirmation when the current
    candle is the pullback/reversal trigger.
    """
    if not volume_ema:
        return False
    for candle in candles[-4:-1]:
        opening = float(candle.get("open", 0) or 0)
        close = float(candle.get("close", 0) or 0)
        volume = float(candle.get("volume", 0) or 0)
        directional = close > opening if side == "CE" else close < opening
        if directional and volume >= volume_ema * threshold:
            return True
    return False


def _level_evidence(structure, side):
    """Return chart-level quality without upgrading a moving fallback into a wall."""
    zone = structure.get(f"{side}_zone") or {}
    # Older/mocked structure providers did not expose quality. Preserve their
    # previous conservative behaviour; the live clustered engine is explicit.
    if not zone:
        return {"source": "legacy", "touches": None, "reliable": True}
    source = str(zone.get("source") or "legacy")
    touches = int(zone.get("touches") or 0)
    reliable = bool(zone.get("reliable", source != "fallback" and touches >= 2))
    return {"source": source, "touches": touches, "reliable": reliable}


def _nearby_unbroken_level(close, chart_level, oi_level, required_room, side, chart_quality, oi_quality=True):
    """Separate repeated/OI walls from one-candle fallback micro-levels."""
    candidates = []
    if chart_level is not None:
        distance = chart_level - close if side == "CE" else close - chart_level
        candidates.append(("chart", chart_level, distance, bool(chart_quality.get("reliable"))))
    if oi_level is not None:
        distance = oi_level - close if side == "CE" else close - oi_level
        candidates.append(("OI", oi_level, distance, bool(oi_quality)))
    ahead = [item for item in candidates if item[2] >= 0]
    nearest = min(ahead, key=lambda item: item[2]) if ahead else None
    hard = nearest if nearest and nearest[2] < required_room and nearest[3] else None
    soft = nearest if nearest and nearest[2] < required_room and not nearest[3] else None
    return nearest, hard, soft


def evaluate_tps_entry_v2(candles, capture, chain=None, settings=None, environment=None):
    """Return independent CE/PE evidence, checklist result and hard blockers."""
    chain, settings = chain or {}, settings or {}
    enabled = [name for name in settings.get("tps_enabled_conditions", DEFAULT_ENABLED) if name in CONDITION_WEIGHTS]
    if not enabled:
        enabled = list(DEFAULT_ENABLED)
    match_mode = settings.get("tps_match_mode", "adaptive")
    requested_required = max(1, min(int(settings.get("tps_required_matches", 5)), len(enabled)))
    minimum_score = max(0, min(int(settings.get("trade_plan_min_score", 95)), 100))

    close = float(capture["close"]); opening = float(capture["open"])
    ema_5, ema_20, ema_50 = (float(capture[key]) for key in ("ema_5", "ema_20", "ema_50"))
    vwap = float(capture["vwap"]) if capture.get("vwap") else None
    trend_line = float(capture["supertrend"])
    atr = float(capture["atr_14"]) if capture.get("atr_14") else max(close * .001, 1)
    rsi = float(capture["rsi_14"]) if capture.get("rsi_14") else None
    volume_ratio = float(capture["volume_ratio"]) if capture.get("volume_ratio") else 0
    volume_ema = float(capture["volume_ema"]) if capture.get("volume_ema") else None
    candle_direction = capture.get("candle_direction", "NEUTRAL")
    structure = analyze_candles(candles)
    structure_state = structure["state"]
    chart_support, chart_resistance = float(structure["support"]), float(structure["resistance"])
    support_quality = _level_evidence(structure, "support")
    resistance_quality = _level_evidence(structure, "resistance")
    oi_support = float(chain["put_support"]) if chain.get("put_support") not in (None, "") else None
    oi_resistance = float(chain["call_resistance"]) if chain.get("call_resistance") not in (None, "") else None
    put_zone = chain.get("put_support_zone") or {}
    call_zone = chain.get("call_resistance_zone") or {}
    chain_quality = float(chain.get("data_quality") or 0)
    oi_support_reliable = bool(oi_support is not None and chain_quality >= 60 and put_zone.get("strength") != "DISTRIBUTED")
    oi_resistance_reliable = bool(oi_resistance is not None and chain_quality >= 60 and call_zone.get("strength") != "DISTRIBUTED")
    pcr_oi, pcr_volume = chain.get("pcr_oi"), chain.get("pcr_volume")
    pcr_oi = float(pcr_oi) if pcr_oi is not None else None
    pcr_volume = float(pcr_volume) if pcr_volume is not None else None
    tolerance = max(atr * .35, close * .0005)
    zones = [ema_5, ema_20] + ([vwap] if vwap is not None else [])
    # Include the just-completed trigger candle.  Excluding it forced the
    # engine to wait one extra 5-minute candle after a valid EMA/VWAP retest.
    trigger_window = candles[-3:]
    recent_bullish_touch = any(any(abs(float(c["low"]) - zone) <= tolerance for zone in zones) for c in trigger_window)
    recent_bearish_touch = any(any(abs(float(c["high"]) - zone) <= tolerance for zone in zones) for c in trigger_window)
    environment = environment or {}
    regime = environment.get("regime")
    environment_ok = not environment or (
        float(environment.get("risk_multiplier", 1)) >= .75 and environment.get("vix_zone") != "EXTREME RISK"
    )
    environment_detail = (
        f"{environment.get('regime', 'unavailable')}; VIX {environment.get('vix_zone', 'unavailable')}; "
        f"risk multiplier {environment.get('risk_multiplier', 1)}"
    )
    volume_threshold = float(environment.get("volume_threshold", 1.5))
    fake_breakout_state = evidence_state(capture.get("fake_breakout_risk"))
    fake_breakout_clear = fake_breakout_state is EvidenceState.FALSE
    candle_range = max(float(capture.get("high") or close) - float(capture.get("low") or close), 1e-9)
    candle_body_ratio = abs(close - opening) / candle_range
    strong_quality = volume_ratio >= volume_threshold and fake_breakout_clear
    ce_recent_impulse = _recent_impulse_volume(candles, volume_ema, volume_threshold, "CE")
    pe_recent_impulse = _recent_impulse_volume(candles, volume_ema, volume_threshold, "PE")
    # A mature directional move often continues on normal participation after
    # its opening impulse. Requiring 1.5x volume on every later candle made the
    # paper engine systematically miss clean trend continuation. This bounded
    # path is available only when structure, VWAP and the full EMA stack agree.
    continuation_threshold = max(.90, min(1.10, float(environment.get("continuation_volume_threshold", 1.0))))
    ce_trend_context = bool(
        regime == "TRENDING" and structure_state.startswith("Bullish")
        and vwap is not None and close > vwap and ema_5 > ema_20 > ema_50
    )
    pe_trend_context = bool(
        regime == "TRENDING" and structure_state.startswith("Bearish")
        and vwap is not None and close < vwap and ema_5 < ema_20 < ema_50
    )
    ce_continuation_volume = bool(
        fake_breakout_clear and ce_trend_context and candle_direction == "BULLISH"
        and volume_ratio >= continuation_threshold
    )
    pe_continuation_volume = bool(
        fake_breakout_clear and pe_trend_context and candle_direction == "BEARISH"
        and volume_ratio >= continuation_threshold
    )
    # SENSEX (and occasionally another thin current-month future) can return
    # only a handful of traded units in a completed five-minute candle.  That
    # is not evidence against an otherwise clean move; it is an unusable
    # sample.  Do not award a volume pass, but do not make sparse broker data
    # consume one of the user's checklist matches either.  A genuinely heavy
    # current/recent impulse remains applicable even when the rolling average
    # is small.
    current_volume = float(capture.get("volume") or 0)
    volume_data_reliable = bool(
        volume_ema and (
            volume_ema >= 100
            or current_volume >= 100
            or ce_recent_impulse
            or pe_recent_impulse
        )
    )
    ce_volume_ok = fake_breakout_clear and (
        (strong_quality and candle_direction == "BULLISH") or (recent_bullish_touch and ce_recent_impulse)
        or ce_continuation_volume
    )
    pe_volume_ok = fake_breakout_clear and (
        (strong_quality and candle_direction == "BEARISH") or (recent_bearish_touch and pe_recent_impulse)
        or pe_continuation_volume
    )
    ce_volume_detail = (
        f"{volume_ratio:.2f}x current Volume EMA20" if strong_quality and candle_direction == "BULLISH"
        else f"{volume_ratio:.2f}x Volume EMA20; regime-aware bullish continuation >= {continuation_threshold:.2f}x"
        if ce_continuation_volume
        else f"recent bullish impulse >= {volume_threshold:.2f}x Volume EMA20 before pullback"
        if ce_recent_impulse else f"{volume_ratio:.2f}x Volume EMA20; no qualifying recent bullish impulse"
    )
    pe_volume_detail = (
        f"{volume_ratio:.2f}x current Volume EMA20" if strong_quality and candle_direction == "BEARISH"
        else f"{volume_ratio:.2f}x Volume EMA20; regime-aware bearish continuation >= {continuation_threshold:.2f}x"
        if pe_continuation_volume
        else f"recent bearish impulse >= {volume_threshold:.2f}x Volume EMA20 before pullback"
        if pe_recent_impulse else f"{volume_ratio:.2f}x Volume EMA20; no qualifying recent bearish impulse"
    )

    common = {
        "CE": [
            _side_condition("Market structure", structure_state.startswith("Bullish"), structure_state),
            _side_condition("Price vs VWAP", vwap is not None and close > vwap, f"Close {close:.2f} > VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable", vwap is not None),
            _side_condition("EMA 5/20/50 alignment", ema_5 > ema_20 > ema_50, f"EMA5 {ema_5:.2f} > EMA20 {ema_20:.2f} > EMA50 {ema_50:.2f}"),
            _side_condition("SuperTrend confirmation", close > trend_line, f"Close {close:.2f} > SuperTrend {trend_line:.2f}"),
            _side_condition("Pullback and reversal", recent_bullish_touch and close > opening, f"EMA/VWAP touch within {tolerance:.2f}; candle {candle_direction}"),
            _side_condition("Directional volume", ce_volume_ok, ce_volume_detail if volume_data_reliable else f"Sparse futures-volume sample ({current_volume:.0f}; EMA20 {volume_ema or 0:.2f}) — excluded, not failed", volume_data_reliable),
            _side_condition("OI/PCR context", pcr_oi is not None and pcr_volume is not None and pcr_oi >= .75 and pcr_volume <= 1.25, f"OI PCR {pcr_oi if pcr_oi is not None else '-'}; Volume PCR {pcr_volume if pcr_volume is not None else '-'}", pcr_oi is not None and pcr_volume is not None),
            _side_condition("Market environment / VIX", environment_ok, environment_detail),
        ],
        "PE": [
            _side_condition("Market structure", structure_state.startswith("Bearish"), structure_state),
            _side_condition("Price vs VWAP", vwap is not None and close < vwap, f"Close {close:.2f} < VWAP {vwap:.2f}" if vwap is not None else "VWAP unavailable", vwap is not None),
            _side_condition("EMA 5/20/50 alignment", ema_5 < ema_20 < ema_50, f"EMA5 {ema_5:.2f} < EMA20 {ema_20:.2f} < EMA50 {ema_50:.2f}"),
            _side_condition("SuperTrend confirmation", close < trend_line, f"Close {close:.2f} < SuperTrend {trend_line:.2f}"),
            _side_condition("Pullback and reversal", recent_bearish_touch and close < opening, f"EMA/VWAP touch within {tolerance:.2f}; candle {candle_direction}"),
            _side_condition("Directional volume", pe_volume_ok, pe_volume_detail if volume_data_reliable else f"Sparse futures-volume sample ({current_volume:.0f}; EMA20 {volume_ema or 0:.2f}) — excluded, not failed", volume_data_reliable),
            _side_condition("OI/PCR context", pcr_oi is not None and pcr_volume is not None and pcr_oi <= 1.25 and pcr_volume >= .80, f"OI PCR {pcr_oi if pcr_oi is not None else '-'}; Volume PCR {pcr_volume if pcr_volume is not None else '-'}", pcr_oi is not None and pcr_volume is not None),
            _side_condition("Market environment / VIX", environment_ok, environment_detail),
        ],
    }

    zone_tolerance = max(atr * 2.5, close * .0025)
    support_gap = abs(chart_support - oi_support) if oi_support is not None else None
    resistance_gap = abs(chart_resistance - oi_resistance) if oi_resistance is not None else None
    support_confluence = support_gap is not None and support_gap <= zone_tolerance
    resistance_confluence = resistance_gap is not None and resistance_gap <= zone_tolerance
    regular_target = float(environment.get("regular_move_target_points") or 0)
    remaining_expected_range = environment.get("remaining_expected_range")
    range_consumed_percent = environment.get("range_consumed_percent")
    movement_state = str(environment.get("movement_state") or "UNAVAILABLE")
    regular_move_available = environment.get("regular_move_available")
    required_room = max(close * .0005, min(atr * .75, regular_target) if regular_target > 0 else atr * .75)
    configured_extension = settings.get("tps_max_entry_extension_atr")
    adaptive_extension = environment.get("max_entry_extension_atr", DEFAULT_MAX_ENTRY_EXTENSION_ATR)
    max_extension_atr = max(.30, min(float(configured_extension if configured_extension is not None else adaptive_extension), 2.0))
    ce_max_rsi = max(60.0, min(float(settings.get("tps_ce_max_rsi", DEFAULT_CE_MAX_RSI)), 90.0))
    pe_min_rsi = max(10.0, min(float(settings.get("tps_pe_min_rsi", DEFAULT_PE_MIN_RSI)), 40.0))
    side_results = {}
    for side in ("CE", "PE"):
        score, selected = _side_score(common[side], enabled)
        applicable_count = len(selected)
        if not applicable_count:
            required, required_reason = 0, "no selected condition is applicable to the current regime/data"
        elif match_mode == "all":
            required, required_reason = applicable_count, "all applicable conditions"
        elif match_mode == "adaptive" and environment:
            # The score threshold already measures evidence strength.  Asking
            # for 90% of the remaining checks in a calm market made one sparse
            # data point an accidental all-or-nothing veto.
            ratio = .75 if regime == "TRENDING" else .85 if regime == "SIDEWAYS / TRANSITION" else .80
            required = max(1, min(applicable_count, ceil(applicable_count * ratio)))
            required_reason = f"adaptive {regime or 'unknown'} regime ({ratio * 100:.0f}% of applicable conditions)"
        else:
            required = max(1, min(requested_required, applicable_count))
            required_reason = f"configured count {required} of applicable conditions"
        passed = sum(item["passed"] for item in selected)
        blockers = []
        quality_warnings = []
        # Checklist selection controls scoring, but these four directional
        # anchors may never be voted away. Premium buying against the actual
        # trend produced misleading high scores in forward testing because
        # unrelated confirmations compensated for a contradictory direction.
        direction_anchor_names = {
            "Market structure", "Price vs VWAP",
            "EMA 5/20/50 alignment", "SuperTrend confirmation",
        }
        direction_anchors = [
            item for item in common[side] if item["name"] in direction_anchor_names
        ]
        missing_direction = [
            item["name"] for item in direction_anchors
            if not item.get("applicable", True) or not item.get("passed", False)
        ]
        if missing_direction:
            blockers.append(
                f"{side} directional consensus is incomplete: "
                + ", ".join(missing_direction)
            )
        if not applicable_count:
            blockers.append("No selected checklist condition is applicable to the current candle")
        unknown_selected = [item for item in common[side] if item["name"] in enabled and not item.get("applicable", True)]
        data_gaps = [f"{item['name']} evidence unavailable: {item['detail']}" for item in unknown_selected]
        if fake_breakout_state is EvidenceState.TRUE:
            blockers.append("Rejection-wick / fake-breakout risk is active")
        elif fake_breakout_state is EvidenceState.UNKNOWN:
            data_gaps.append("Fake-breakout evidence unavailable")
        if side == "CE":
            trigger_ok = recent_bullish_touch and close > opening and candle_direction == "BULLISH"
            timing_reference = max(level for level in (ema_20, vwap) if level is not None)
            extension_points = max(0.0, close - timing_reference)
            extension_atr = extension_points / atr
            nearest_evidence, hard_level, soft_level = _nearby_unbroken_level(
                close, chart_resistance, oi_resistance, required_room, side, resistance_quality, oi_resistance_reliable,
            )
            nearest = nearest_evidence[1] if nearest_evidence else None
            room = nearest_evidence[2] if nearest_evidence else None
            if nearest is None and chart_resistance is None and oi_resistance is None:
                blockers.append("Resistance level is unavailable")
            elif nearest is None:
                quality_warnings.append("Known resistance levels are already broken; no nearby unbroken resistance wall")
            elif hard_level:
                blockers.append(f"CE entry is too close to reliable {hard_level[0]} resistance ({room:.2f} < {required_room:.2f} points room)")
            elif soft_level:
                quality_warnings.append(f"Nearby single-touch/fallback chart resistance ({room:.2f} points) is observation only, not a hard wall")
            extension_hard_limit = min(2.0, max_extension_atr * 1.25)
            if extension_atr > extension_hard_limit:
                blockers.append(f"Late CE entry: price is {extension_atr:.2f} ATR above VWAP/EMA20 (hard limit {extension_hard_limit:.2f})")
            elif extension_atr > max_extension_atr:
                if trigger_ok and regular_move_available is not False:
                    quality_warnings.append(f"CE extension {extension_atr:.2f} ATR is above preferred {max_extension_atr:.2f}, but within the fresh-trigger grace band")
                elif trigger_ok:
                    blockers.append(
                        f"Late CE entry after expected range exhaustion: {extension_atr:.2f} ATR extension exceeds the "
                        f"preferred {max_extension_atr:.2f}; only {remaining_expected_range if remaining_expected_range is not None else '-'} "
                        f"expected points remain ({movement_state})"
                    )
                else:
                    blockers.append(f"Late CE entry: {extension_atr:.2f} ATR extension has no fresh pullback/reversal trigger")
            if rsi is not None and rsi >= ce_max_rsi:
                blockers.append(f"Late CE entry: RSI {rsi:.1f} is above the {ce_max_rsi:.1f} chase limit")
            if not trigger_ok:
                quality_warnings.append("No fresh bullish EMA/VWAP pullback-and-reversal trigger; checklist/score must qualify without it")
        else:
            trigger_ok = recent_bearish_touch and close < opening and candle_direction == "BEARISH"
            timing_reference = min(level for level in (ema_20, vwap) if level is not None)
            extension_points = max(0.0, timing_reference - close)
            extension_atr = extension_points / atr
            nearest_evidence, hard_level, soft_level = _nearby_unbroken_level(
                close, chart_support, oi_support, required_room, side, support_quality, oi_support_reliable,
            )
            nearest = nearest_evidence[1] if nearest_evidence else None
            room = nearest_evidence[2] if nearest_evidence else None
            if nearest is None and chart_support is None and oi_support is None:
                blockers.append("Support level is unavailable")
            elif nearest is None:
                quality_warnings.append("Known support levels are already broken; no nearby unbroken support wall")
            elif hard_level:
                blockers.append(f"PE entry is too close to reliable {hard_level[0]} support ({room:.2f} < {required_room:.2f} points room)")
            elif soft_level:
                quality_warnings.append(f"Nearby single-touch/fallback chart support ({room:.2f} points) is observation only, not a hard wall")
            extension_hard_limit = min(2.0, max_extension_atr * 1.25)
            if extension_atr > extension_hard_limit:
                blockers.append(f"Late PE entry: price is {extension_atr:.2f} ATR below VWAP/EMA20 (hard limit {extension_hard_limit:.2f})")
            elif extension_atr > max_extension_atr:
                if trigger_ok and regular_move_available is not False:
                    quality_warnings.append(f"PE extension {extension_atr:.2f} ATR is above preferred {max_extension_atr:.2f}, but within the fresh-trigger grace band")
                elif trigger_ok:
                    blockers.append(
                        f"Late PE entry after expected range exhaustion: {extension_atr:.2f} ATR extension exceeds the "
                        f"preferred {max_extension_atr:.2f}; only {remaining_expected_range if remaining_expected_range is not None else '-'} "
                        f"expected points remain ({movement_state})"
                    )
                else:
                    blockers.append(f"Late PE entry: {extension_atr:.2f} ATR extension has no fresh pullback/reversal trigger")
            if rsi is not None and rsi <= pe_min_rsi:
                blockers.append(f"Late PE entry: RSI {rsi:.1f} is below the {pe_min_rsi:.1f} chase limit")
            if not trigger_ok:
                quality_warnings.append("No fresh bearish EMA/VWAP pullback-and-reversal trigger; checklist/score must qualify without it")
        checklist_matched = applicable_count > 0 and passed >= required
        score_matched = score >= minimum_score
        blockers = unique_messages(blockers)
        quality_warnings = unique_messages(quality_warnings)
        # In explicit PAPER testing, record a decisive reversal as a separate
        # validation thesis instead of staying attached to the slower EMA
        # stack. Real execution and every risk/data gate remain unchanged.
        crosses_vwap = bool(
            vwap is not None and (
                opening <= vwap < close if side == "CE" else opening >= vwap > close
            )
        )
        fast_side_confirmed = bool(
            close > ema_5 and close > trend_line if side == "CE"
            else close < ema_5 and close < trend_line
        )
        expected_direction = "BULLISH" if side == "CE" else "BEARISH"
        allowed_slow_misses = {"Market structure", "EMA 5/20/50 alignment"}
        risk_blockers = [item for item in blockers if not item.startswith(f"{side} directional consensus is incomplete:")]
        impulse_reversal = bool(
            settings.get("paper_validation_testing_mode")
            and fake_breakout_clear and candle_direction == expected_direction
            and candle_body_ratio >= .70 and volume_ratio >= max(2.0, volume_threshold)
            and crosses_vwap and fast_side_confirmed
            and set(missing_direction).issubset(allowed_slow_misses)
            and not risk_blockers and not data_gaps
            and regular_move_available is not False
        )
        ready = checklist_matched and score_matched and not blockers and not data_gaps
        side_results[side] = {
            "candidate": side, "confirmations": common[side], "selected_confirmations": selected,
            "not_applicable_confirmations": [item for item in common[side] if item["name"] in enabled and not item.get("applicable", True)],
            "passed": passed, "total": len(selected), "required": required, "score": score,
            "checklist_matched": checklist_matched, "score_matched": score_matched,
            "hard_blockers": blockers, "quality_warnings": quality_warnings, "trade_ready": ready,
            "risk_blockers": risk_blockers,
            "impulse_reversal_validation": {
                "passed": impulse_reversal, "paper_only": True,
                "body_ratio": round(candle_body_ratio, 2), "volume_ratio": round(volume_ratio, 2),
                "crossed_vwap": crosses_vwap, "fast_side_confirmed": fast_side_confirmed,
                "slow_context_misses": missing_direction,
            },
            "directional_consensus": {
                "passed": not missing_direction,
                "required": sorted(direction_anchor_names),
                "missing": missing_direction,
            },
            "data_gaps": data_gaps,
            "evidence_states": {item["name"]: item["evidence_state"] for item in common[side] if item["name"] in enabled},
            "primary_blocker": blockers[0] if blockers else data_gaps[0] if data_gaps else None,
            "secondary_warnings": unique_messages(blockers[1:] + data_gaps[1:] + quality_warnings),
            "required_reason": required_reason,
            "entry_quality": {
                "reference": timing_reference, "extension_points": round(extension_points, 2),
                "extension_atr": round(extension_atr, 2), "maximum_extension_atr": max_extension_atr,
                "rsi": rsi, "rsi_limit": ce_max_rsi if side == "CE" else pe_min_rsi,
                "fresh_pullback_reversal": trigger_ok,
                "required_room_points": round(required_room, 2),
                "regular_move_target_points": round(regular_target, 2) if regular_target else None,
                "nearest_level": nearest, "room_to_level": round(room, 2) if room is not None else None,
                "chart_level_quality": resistance_quality if side == "CE" else support_quality,
                "environment_regime": environment.get("regime", "unavailable"),
                "movement_state": movement_state,
                "range_consumed_percent": range_consumed_percent,
                "remaining_expected_range": remaining_expected_range,
                "regular_move_available": regular_move_available,
                "timely": extension_atr <= extension_hard_limit and (
                    rsi is None or (rsi < ce_max_rsi if side == "CE" else rsi > pe_min_rsi)
                ) and trigger_ok,
            },
            "state": "EXECUTE" if ready else "DATA GAP" if data_gaps else "REJECTED" if blockers else "WATCH",
        }

    ce, pe = side_results["CE"], side_results["PE"]
    valid = [side for side in (ce, pe) if side["trade_ready"]]
    if len(valid) == 1:
        selected = valid[0]; direction = "BULLISH" if selected["candidate"] == "CE" else "BEARISH"
    elif len(valid) == 2:
        selected = max(valid, key=lambda item: item["score"]); direction = "CONFLICT / HEDGE WATCH"
        selected = {**selected, "trade_ready": False, "hard_blockers": selected["hard_blockers"] + ["Both CE and PE passed; conflict requires hedge/manual review"]}
    else:
        reversal = [side for side in (ce, pe) if (side.get("impulse_reversal_validation") or {}).get("passed")]
        selected = reversal[0] if len(reversal) == 1 else max((ce, pe), key=lambda item: (item["score"], item["passed"]))
        direction = "BULLISH WATCH" if selected["candidate"] == "CE" else "BEARISH WATCH" if selected["candidate"] == "PE" else "MIXED"

    return {
        "version": "TPS Entry Confirmation System v3 - independent CE/PE",
        "direction": direction, "candidate": selected["candidate"], "side_evaluations": side_results,
        "confirmations": selected["confirmations"], "selected_confirmations": selected["selected_confirmations"],
        "passed": selected["passed"], "required": selected["required"], "total": selected["total"], "score": selected["score"],
        "minimum_score": minimum_score, "enabled_conditions": enabled,
        "match_mode": match_mode, "required_reason": selected["required_reason"],
        "trade_ready": bool(selected["trade_ready"]),
        "decision": f"TPS V3 {selected['candidate']} PAPER ENTRY CONFIRMED" if selected["trade_ready"] else f"{selected['candidate']} {selected['state']}",
        "blockers": selected["hard_blockers"], "hard_blockers": selected["hard_blockers"],
        "quality_warnings": selected.get("quality_warnings", []),
        "data_gaps": selected.get("data_gaps", []),
        "primary_blocker": selected.get("primary_blocker"),
        "secondary_warnings": selected.get("secondary_warnings", []),
        "evidence_states": {**selected.get("evidence_states", {}), "Fake-breakout risk": fake_breakout_state.value},
        "pcr_oi": pcr_oi, "pcr_volume": pcr_volume, "structure_state": structure_state,
        "market_environment": environment,
        "zones": {"chart_support": chart_support, "chart_resistance": chart_resistance,
                  "oi_support": oi_support, "oi_resistance": oi_resistance,
                  "support_gap": support_gap, "resistance_gap": resistance_gap,
                  "tolerance": zone_tolerance, "support_confluence": support_confluence,
                  "resistance_confluence": resistance_confluence,
                  "support_quality": support_quality, "resistance_quality": resistance_quality,
                  "oi_support_zone": put_zone, "oi_resistance_zone": call_zone,
                  "oi_support_reliable": oi_support_reliable,
                  "oi_resistance_reliable": oi_resistance_reliable,
                  "option_chain_quality": chain_quality},
    }
