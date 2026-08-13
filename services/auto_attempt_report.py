"""Readable rendering for persisted automatic paper-trade evaluations."""


def format_auto_paper_attempt(result):
    if isinstance(result, str):
        return result
    attempt = result.get("attempt") or {}
    capture = attempt.get("capture") or {}
    chart = attempt.get("chart") or {}
    lines = [result.get("status", "Auto paper cycle completed.")]
    lines.append(f"Checked at: {attempt.get('checked_at') or 'Unavailable'} | Candle time: {attempt.get('candle_time') or 'Not evaluated'} | Future: {attempt.get('future_symbol') or 'Not loaded'}")
    timing = attempt.get("timing") or {}
    if timing:
        lines.append(
            f"Signal timing: {timing.get('stage', 'NONE')} | Discovered {timing.get('signal_discovery_at') or '-'} | "
            f"First valid {timing.get('first_valid_trigger_at') or '-'} | Final capture {timing.get('final_capture_at') or '-'} | "
            f"Delay {timing.get('delay_seconds') if timing.get('delay_seconds') is not None else '-'} sec | "
            f"No-look-ahead {'YES' if timing.get('no_look_ahead') else 'NO'}"
        )
    if capture:
        lines.extend((
            f"OHLC: O {capture.get('open', '-')} | H {capture.get('high', '-')} | L {capture.get('low', '-')} | C {capture.get('close', '-')}",
            f"Trend values: EMA 5 {capture.get('ema_5', '-')} | EMA 20 {capture.get('ema_20', '-')} | EMA 50 {capture.get('ema_50', '-')} | VWAP {capture.get('vwap', '-')} | SuperTrend {capture.get('supertrend', '-')} ({capture.get('supertrend_state', '-')})",
            f"Momentum: RSI 14 {capture.get('rsi_14', '-')} | ATR 14 {capture.get('atr_14', '-')} | Candle {capture.get('candle_direction', '-')}",
            f"Volume: {capture.get('volume', '-')} | Volume EMA 20: {capture.get('volume_ema', '-')} | Ratio: {capture.get('volume_ratio', '-')}x | {capture.get('volume_signal', '-')}",
        ))
    if chart:
        strategy = chart.get("strategy") or {}
        environment = strategy.get("market_environment") or chart.get("market_environment") or {}
        sides = strategy.get("side_evaluations") or {}
        ce, pe = sides.get("CE") or {}, sides.get("PE") or {}
        lines.append(
            f"Decision: {chart.get('decision', '-')} | Candidate: {attempt.get('candidate') or '-'} | "
            f"CE score {ce.get('score', '-')} ({ce.get('passed', '-')}/{ce.get('total', '-')}) | "
            f"PE score {pe.get('score', '-')} ({pe.get('passed', '-')}/{pe.get('total', '-')}) | "
                f"Required: {strategy.get('required', '-')} matches + score {strategy.get('minimum_score', '-')} | "
                f"{strategy.get('required_reason', strategy.get('match_mode', '-'))}"
        )
        confirmations = strategy.get("confirmations") or []
        if confirmations:
            lines.append("Selected-side checklist evidence:")
            lines.extend(f"{'PASS' if item['passed'] else 'FAIL'} - {item['name']}: {item['detail']}" for item in confirmations)
        zones = strategy.get("zones") or {}
        if zones:
            lines.append(
                f"Zone confluence: Chart support {zones.get('chart_support', '-')} vs Put-OI support {zones.get('oi_support', '-')} "
                f"({'MATCH' if zones.get('support_confluence') else 'NOT ALIGNED'}) | Chart resistance {zones.get('chart_resistance', '-')} "
                f"vs Call-OI resistance {zones.get('oi_resistance', '-')} ({'MATCH' if zones.get('resistance_confluence') else 'NOT ALIGNED'}) | "
                f"Tolerance {zones.get('tolerance', '-')}"
            )
        selected_side = sides.get(attempt.get("candidate")) or {}
        entry_quality = selected_side.get("entry_quality") or {}
        if entry_quality:
            lines.append(
                f"Entry timing: {'TIMELY' if entry_quality.get('timely') else 'LATE / EXTENDED'} | "
                f"Distance {entry_quality.get('extension_points')} points = {entry_quality.get('extension_atr')} ATR "
                f"(maximum {entry_quality.get('maximum_extension_atr')} ATR) | RSI {entry_quality.get('rsi')} | "
                f"Fresh pullback/reversal {'YES' if entry_quality.get('fresh_pullback_reversal') else 'NO'}"
            )
        reasons = chart.get("reasons") or []
        if reasons:
            lines.append("Conditions passed: " + "; ".join(reasons))
        if environment:
            lines.append(
                f"Market environment: {environment.get('regime')} | VIX {environment.get('vix') or 'Unavailable'} "
                f"({environment.get('vix_zone')}) | ATR {environment.get('atr_percent')}% | "
                f"Risk multiplier {environment.get('risk_multiplier')} | Strike {environment.get('strike_preference')}"
            )
            lines.append(
                f"Opening range {environment.get('opening_range_low')} - {environment.get('opening_range_high')} | "
                f"Previous day H/L {environment.get('previous_day_high')} / {environment.get('previous_day_low')} | "
                f"{environment.get('gap_state')} {environment.get('gap_points')} | "
                f"Strategy {(environment.get('expiry_strategy') or {}).get('strategy', environment.get('strategy_preference'))}"
            )
            lines.append(
                f"VIX range budget: expected {environment.get('expected_daily_range')} points | "
                f"session used {environment.get('session_range')} ({environment.get('range_consumed_percent')}%) | "
                f"remaining {environment.get('remaining_expected_range')} | regular objective "
                f"{environment.get('regular_move_target_points')} points | adaptive extension "
                f"{environment.get('max_entry_extension_atr')} ATR"
            )
            event = environment.get("event_risk") or {}
            lines.append(f"Economic calendar: {event.get('status', 'Unavailable')} | Feed available {event.get('available', False)}")
            lines.extend(
                f"Event: {item.get('name')} | {item.get('country')} | {item.get('time')} | impact {item.get('importance')} | "
                f"forecast {item.get('forecast') or '-'} | actual {item.get('actual') or '-'} | previous {item.get('previous') or '-'} | "
                f"{item.get('minutes_from_now')} min"
                for item in event.get("nearby_events", [])[:5]
            )
    proposed = result.get("proposed_plan") or result.get("plan") or {}
    safety = proposed.get("execution_safety") or {}
    if safety:
        lines.append(
            f"Execution safety: {'PASS' if safety.get('allowed') else 'BLOCKED'} | R:R {safety.get('rr_ratio')} | "
            f"Spread {safety.get('spread_percent')}%"
        )
    chain = attempt.get("chain") or {}
    if chain:
        oi_pcr = f"{chain['pcr_oi']:.2f}" if chain.get("pcr_oi") is not None else "Unavailable"
        volume_pcr = f"{chain['pcr_volume']:.2f}" if chain.get("pcr_volume") is not None else "Unavailable"
        lines.append(f"Option chain: OI PCR {oi_pcr} | Volume PCR {volume_pcr} | Put support {chain.get('put_support', '-')} | Call resistance {chain.get('call_resistance', '-')} | {chain.get('context', '')}")
    blockers = attempt.get("blockers") or []
    lines.append("Why trade was not captured: " + ("; ".join(dict.fromkeys(blockers)) if blockers else "All strict conditions passed; paper trade was captured."))
    return "\n".join(lines)
