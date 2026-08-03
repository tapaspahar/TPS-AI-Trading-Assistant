"""Deterministic candle-by-candle validation for the TPS chart rule set.

This module is intentionally a paper simulation.  It never sends orders and
does not model broker slippage, spreads, taxes, or option premium behaviour.
"""
from __future__ import annotations

from datetime import datetime

from engine.live_setup_capture import analyse_volume_candle, atr, ema, rsi, supertrend


def _session_vwap(candles):
    """Calculate VWAP only from candles in the latest candle's trading date."""
    try:
        session_date = datetime.fromisoformat(str(candles[-1]["time"])).date()
        session = [candle for candle in candles if datetime.fromisoformat(str(candle["time"])).date() == session_date]
    except (ValueError, TypeError, KeyError):
        session = candles
    total_volume = sum(float(candle.get("volume", 0) or 0) for candle in session)
    if total_volume <= 0:
        return None
    return sum(
        ((float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3) * float(candle.get("volume", 0) or 0)
        for candle in session
    ) / total_volume


def _close_trade(direction, entry, stoploss, target, candle):
    """Use a conservative stop-first rule when both levels occur in one candle."""
    high, low = float(candle["high"]), float(candle["low"])
    if direction == "LONG":
        if low <= stoploss:
            return stoploss, "STOP LOSS"
        if high >= target:
            return target, "TARGET"
    else:
        if high >= stoploss:
            return stoploss, "STOP LOSS"
        if low <= target:
            return target, "TARGET"
    return None


def run_tps_backtest(candles, max_holding_bars=12):
    """Simulate the TPS EMA/VWAP/SuperTrend/RSI/ATR setup on OHLCV candles."""
    if len(candles) < 80:
        raise ValueError("At least 80 candles are needed to run this backtest.")
    trades = []
    index = 60
    while index < len(candles) - 1:
        history = candles[: index + 1]
        latest = history[-1]
        closes = [float(candle["close"]) for candle in history]
        volumes = [float(candle.get("volume", 0) or 0) for candle in history]
        price = closes[-1]
        ema_5, ema_20, ema_50 = ema(closes[-20:], 5), ema(closes[-50:], 20), ema(closes[-60:], 50)
        trend_line = supertrend(history[-60:])
        rsi_value, atr_value = rsi(closes), atr(history[-20:])
        vwap_value = _session_vwap(history)
        volume_ema = ema(volumes[-20:], 20) if any(volumes[-20:]) else None
        volume_data = analyse_volume_candle(history)
        volume_ok = not volume_data["fake_breakout_risk"] and volume_data["volume_ratio"] is not None and volume_data["volume_ratio"] >= 1.5
        long_signal = price > trend_line and ema_5 > ema_20 > ema_50 and 50 <= rsi_value <= 70 and volume_ok and volume_data["candle_direction"] == "BULLISH"
        short_signal = price < trend_line and ema_5 < ema_20 < ema_50 and 30 <= rsi_value <= 50 and volume_ok and volume_data["candle_direction"] == "BEARISH"
        if vwap_value is not None:
            long_signal = long_signal and price > vwap_value
            short_signal = short_signal and price < vwap_value
        if not long_signal and not short_signal:
            index += 1
            continue

        direction = "LONG" if long_signal else "SHORT"
        entry = price
        risk = max(atr_value, entry * 0.002)
        stoploss = entry - risk if direction == "LONG" else entry + risk
        target = entry + risk * 2 if direction == "LONG" else entry - risk * 2
        exit_price, outcome, exit_index = None, "TIME EXIT", min(index + max_holding_bars, len(candles) - 1)
        for future_index in range(index + 1, exit_index + 1):
            closed = _close_trade(direction, entry, stoploss, target, candles[future_index])
            if closed:
                exit_price, outcome = closed
                exit_index = future_index
                break
        if exit_price is None:
            exit_price = float(candles[exit_index]["close"])
        pnl_points = exit_price - entry if direction == "LONG" else entry - exit_price
        trades.append({
            "time": str(latest["time"]), "direction": direction, "entry": round(entry, 2),
            "stoploss": round(stoploss, 2), "target": round(target, 2),
            "exit": round(exit_price, 2), "outcome": outcome, "pnl_points": round(pnl_points, 2),
            "rsi_14": round(rsi_value, 2), "atr_14": round(atr_value, 2),
            "volume_ratio": round(volume_data["volume_ratio"], 2),
        })
        index = exit_index + 1

    wins = sum(1 for trade in trades if trade["pnl_points"] > 0)
    losses = sum(1 for trade in trades if trade["pnl_points"] < 0)
    gross_profit = sum(trade["pnl_points"] for trade in trades if trade["pnl_points"] > 0)
    gross_loss = abs(sum(trade["pnl_points"] for trade in trades if trade["pnl_points"] < 0))
    equity, peak, max_drawdown = 0.0, 0.0, 0.0
    for trade in trades:
        equity += trade["pnl_points"]
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "trades": trades, "total_trades": len(trades), "wins": wins, "losses": losses,
        "win_rate": round((wins / len(trades)) * 100, 1) if trades else 0.0,
        "net_points": round(sum(trade["pnl_points"] for trade in trades), 2),
        "max_drawdown_points": round(max_drawdown, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else (99.0 if gross_profit else 0.0),
        "research_status": _research_status(len(trades), wins, losses, gross_profit, gross_loss),
        "volume_available": any(float(candle.get("volume", 0) or 0) > 0 for candle in candles),
    }


def _research_status(total, wins, losses, gross_profit, gross_loss):
    """State evidence quality; deliberately never turn a backtest into a guarantee."""
    decisive = wins + losses
    win_rate = (wins / decisive) * 100 if decisive else 0
    profit_factor = gross_profit / gross_loss if gross_loss else (99 if gross_profit else 0)
    if total < 30:
        return "Insufficient sample: collect at least 30 paper signals before judging the rule."
    if win_rate >= 55 and profit_factor >= 1.2:
        return "Promising historical sample only: forward-test with small risk; no win-rate guarantee."
    return "Historical rules are not validated for this sample: do not increase risk."
