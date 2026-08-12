"""TPS Powerful Engine: selective, multi-evidence options signal controller.

The controller deliberately separates historically validated next-candle purity
from live confluence strength.  It publishes only when independent evidence
layers agree and otherwise abstains.  No score returned here is a guaranteed
win probability.
"""
from __future__ import annotations


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_powerful_engine(*, pre_candle, capture, multi_timeframe, smart_money,
                             chain, environment, option_quote=None):
    votes = []

    def add(layer, side, weight, detail, available=True):
        votes.append({"layer": layer, "side": side, "weight": float(weight),
                      "detail": detail, "available": bool(available)})

    # 1. Leakage-safe, walk-forward validated Candle DNA prediction.
    pre_side = "CE" if pre_candle.get("prediction") == "BULLISH" else "PE" if pre_candle.get("prediction") == "BEARISH" else "NEUTRAL"
    pre_ready = bool(pre_candle.get("validation_ready")) and float(pre_candle.get("validated_purity", 0)) >= 60
    add("Candle DNA", pre_side if pre_ready else "NEUTRAL", 24,
        f"{pre_candle.get('prediction')} {pre_candle.get('confidence', 0):.1f}% | walk-forward purity {pre_candle.get('validated_purity', 0):.1f}% over {pre_candle.get('validation_signals', 0)} signals",
        pre_ready)

    # 2. Multi-timeframe structure.
    mtf_context = str(multi_timeframe.get("context", ""))
    mtf_side = "CE" if mtf_context.startswith("Bullish") else "PE" if mtf_context.startswith("Bearish") else "NEUTRAL"
    add("Multi-timeframe", mtf_side, 20, mtf_context, bool(mtf_context))

    # 3. Strict EMA stack.
    e5, e20, e50 = (_number(capture.get(key)) for key in ("ema_5", "ema_20", "ema_50"))
    ema_side = "CE" if None not in (e5, e20, e50) and e5 > e20 > e50 else "PE" if None not in (e5, e20, e50) and e5 < e20 < e50 else "NEUTRAL"
    add("EMA regime", ema_side, 14, f"EMA5 {e5} | EMA20 {e20} | EMA50 {e50}", None not in (e5, e20, e50))

    # 4. VWAP and SuperTrend are grouped to avoid double-counting one price.
    close, vwap, supertrend = (_number(capture.get(key)) for key in ("close", "vwap", "supertrend"))
    price_votes = []
    if close is not None and vwap is not None: price_votes.append("CE" if close > vwap else "PE")
    if close is not None and supertrend is not None: price_votes.append("CE" if close > supertrend else "PE")
    price_side = price_votes[0] if len(price_votes) == 2 and len(set(price_votes)) == 1 else "NEUTRAL"
    add("VWAP + SuperTrend", price_side, 12,
        f"Close {close} | VWAP {vwap} | SuperTrend {supertrend}; votes {price_votes or 'unavailable'}",
        bool(price_votes))

    # 5. Price action / SMC evidence must already be internally scored.
    sm_direction = smart_money.get("direction")
    sm_score = float(smart_money.get("score", 0) or 0)
    sm_side = "CE" if sm_direction == "BULLISH" and sm_score >= 50 else "PE" if sm_direction == "BEARISH" and sm_score >= 50 else "NEUTRAL"
    add("Price action", sm_side, 12,
        f"{sm_direction} {sm_score:.0f}/100 | {smart_money.get('structure')} | {smart_money.get('event') or 'no event'}",
        bool(sm_direction))

    # 6. Directional volume is confirmation, never a standalone direction.
    volume_ratio = _number(capture.get("volume_ratio"))
    volume_threshold = float(environment.get("volume_threshold", 1.5) or 1.5)
    candle_direction = capture.get("candle_direction")
    volume_side = "CE" if volume_ratio is not None and volume_ratio >= volume_threshold and candle_direction == "BULLISH" else "PE" if volume_ratio is not None and volume_ratio >= volume_threshold and candle_direction == "BEARISH" else "NEUTRAL"
    add("Directional volume", volume_side, 10,
        f"{volume_ratio if volume_ratio is not None else 'unavailable'}x EMA20; required {volume_threshold:.2f}x; candle {candle_direction}",
        volume_ratio is not None)

    # 7. OI is deliberately a contextual, lower-weight vote.
    pcr = _number(chain.get("pcr_oi"))
    oi_side = "CE" if pcr is not None and pcr >= 1.10 else "PE" if pcr is not None and pcr <= 0.90 else "NEUTRAL"
    add("Option OI", oi_side, 8,
        f"OI PCR {pcr if pcr is not None else 'unavailable'} | Put support {chain.get('put_support')} | Call resistance {chain.get('call_resistance')} | Focused max pain {chain.get('focused_max_pain')} | ATM expected move {chain.get('expected_move')} | Chain quality {chain.get('data_quality', 0)}/100",
        pcr is not None)

    available_weight = sum(item["weight"] for item in votes if item["available"])
    ce_weight = sum(item["weight"] for item in votes if item["available"] and item["side"] == "CE")
    pe_weight = sum(item["weight"] for item in votes if item["available"] and item["side"] == "PE")
    ce_strength = ce_weight / available_weight * 100 if available_weight else 0
    pe_strength = pe_weight / available_weight * 100 if available_weight else 0
    side = "CE" if ce_strength > pe_strength else "PE" if pe_strength > ce_strength else "NEUTRAL"
    dominant = max(ce_strength, pe_strength)
    margin = abs(ce_strength - pe_strength)
    supporting = [item for item in votes if item["available"] and item["side"] == side]
    opposing = [item for item in votes if item["available"] and item["side"] not in (side, "NEUTRAL")]
    missing = [item["layer"] for item in votes if not item["available"]]

    blockers = []
    if not pre_ready: blockers.append("Candle DNA has not proved 60%+ walk-forward purity on at least 15 eligible historical signals")
    elif pre_side != side: blockers.append(f"Candle DNA predicts {pre_side}, conflicting with dominant {side} evidence")
    if ema_side != side: blockers.append(f"Strict EMA stack does not confirm {side}")
    if mtf_side not in (side, "NEUTRAL"): blockers.append(f"Multi-timeframe structure opposes {side}")
    if price_side != side: blockers.append(f"VWAP and SuperTrend are not jointly aligned for {side}")
    if len(supporting) < 4: blockers.append(f"Only {len(supporting)} independent evidence layers support {side}; minimum 4")
    if dominant < 70 or margin < 25: blockers.append(f"Confluence {dominant:.1f}% / separation {margin:.1f}% is below 70% / 25% gate")
    if environment.get("vix_zone") == "EXTREME RISK": blockers.append("India VIX is in the EXTREME RISK zone")
    if environment.get("regular_move_available") is False: blockers.append("VIX-implied daily range is substantially consumed")
    if int(chain.get("quoted_contracts", 0) or 0) < 6: blockers.append("Fewer than 6 option contracts have usable live quotes")

    liquidity = option_quote or {}
    ltp, bid, ask, option_volume = (_number(liquidity.get(key)) for key in ("ltp", "bid", "ask", "volume"))
    spread_percent = ((ask - bid) / ltp * 100) if None not in (ltp, bid, ask) and ltp > 0 and ask >= bid > 0 else None
    if option_quote is not None:
        if spread_percent is None or spread_percent > 8: blockers.append("ATM option bid/ask spread is unavailable or above 8%")
        if not option_volume or option_volume <= 0: blockers.append("ATM option has no usable traded volume")

    published = side != "NEUTRAL" and not blockers
    signal = f"POWERFUL {side} SIGNAL" if published else "WAIT - POWERFUL ENGINE ABSTAINS"
    return {
        "signal": signal, "candidate": side if side != "NEUTRAL" else None, "published": published,
        "ce_strength": round(ce_strength, 1), "pe_strength": round(pe_strength, 1),
        "dominant_strength": round(dominant, 1), "separation": round(margin, 1),
        "supporting_layers": len(supporting), "opposing_layers": len(opposing),
        "evidence": votes, "blockers": blockers, "missing_layers": missing,
        "validated_pre_candle_purity": float(pre_candle.get("validated_purity", 0) or 0),
        "validated_pre_candle_signals": int(pre_candle.get("validation_signals", 0) or 0),
        "vix": environment.get("vix"), "vix_zone": environment.get("vix_zone"),
        "regime": environment.get("regime"), "spread_percent": spread_percent,
        "expected_move": chain.get("expected_move"), "expected_low": chain.get("expected_low"),
        "expected_high": chain.get("expected_high"), "focused_max_pain": chain.get("focused_max_pain"),
        "chain_data_quality": chain.get("data_quality"), "atm_iv": chain.get("atm_iv"),
        "warning": "Confluence strength is not win probability. A published signal still requires paper validation and manual risk review.",
    }
