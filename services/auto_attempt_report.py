"""Readable rendering for persisted automatic paper-trade evaluations."""


def format_auto_paper_attempt(result):
    if isinstance(result, str):
        return result
    attempt = result.get("attempt") or {}
    capture = attempt.get("capture") or {}
    chart = attempt.get("chart") or {}
    lines = [result.get("status", "Auto paper cycle completed.")]
    lines.append(f"Checked at: {attempt.get('checked_at') or 'Unavailable'} | Candle time: {attempt.get('candle_time') or 'Not evaluated'} | Future: {attempt.get('future_symbol') or 'Not loaded'}")
    if capture:
        lines.extend((
            f"OHLC: O {capture.get('open', '-')} | H {capture.get('high', '-')} | L {capture.get('low', '-')} | C {capture.get('close', '-')}",
            f"Trend values: EMA 5 {capture.get('ema_5', '-')} | EMA 20 {capture.get('ema_20', '-')} | EMA 50 {capture.get('ema_50', '-')} | VWAP {capture.get('vwap', '-')} | SuperTrend {capture.get('supertrend', '-')} ({capture.get('supertrend_state', '-')})",
            f"Momentum: RSI 14 {capture.get('rsi_14', '-')} | ATR 14 {capture.get('atr_14', '-')} | Candle {capture.get('candle_direction', '-')}",
            f"Volume: {capture.get('volume', '-')} | Volume EMA 20: {capture.get('volume_ema', '-')} | Ratio: {capture.get('volume_ratio', '-')}x | {capture.get('volume_signal', '-')}",
        ))
    if chart:
        strategy = chart.get("strategy") or {}
        lines.append(f"Decision: {chart.get('decision', '-')} | Direction: {chart.get('direction', '-')} | Candidate: {attempt.get('candidate') or '-'} | TPS v2 confirmations: {strategy.get('passed', '-')}/6 (minimum 5/6) | Score: {chart.get('score', '-')}/100")
        confirmations = strategy.get("confirmations") or []
        if confirmations:
            lines.append("TPS v2 checklist:")
            lines.extend(f"{'PASS' if item['passed'] else 'FAIL'} - {item['name']}: {item['detail']}" for item in confirmations)
        reasons = chart.get("reasons") or []
        if reasons:
            lines.append("Conditions passed: " + "; ".join(reasons))
    chain = attempt.get("chain") or {}
    if chain:
        oi_pcr = f"{chain['pcr_oi']:.2f}" if chain.get("pcr_oi") is not None else "Unavailable"
        volume_pcr = f"{chain['pcr_volume']:.2f}" if chain.get("pcr_volume") is not None else "Unavailable"
        lines.append(f"Option chain: OI PCR {oi_pcr} | Volume PCR {volume_pcr} | Put support {chain.get('put_support', '-')} | Call resistance {chain.get('call_resistance', '-')} | {chain.get('context', '')}")
    blockers = attempt.get("blockers") or []
    lines.append("Why trade was not captured: " + ("; ".join(dict.fromkeys(blockers)) if blockers else "All strict conditions passed; paper trade was captured."))
    return "\n".join(lines)
