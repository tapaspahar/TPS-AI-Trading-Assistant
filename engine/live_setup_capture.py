"""Build the TPS indicator profile from verified Angel One OHLCV candles."""
from __future__ import annotations

from datetime import datetime


INSTRUMENTS = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "SENSEX": ("BSE", "99919000"),
}
TIMEFRAMES = {
    "5m": ("FIVE_MINUTE", 5),
    "15m": ("FIFTEEN_MINUTE", 15),
    "1h": ("ONE_HOUR", 60),
    "1D": ("ONE_DAY", 365),
}


def ema(values, period):
    if not values:
        raise ValueError("No values available for indicator calculation.")
    multiplier = 2 / (period + 1)
    result = float(values[0])
    for value in values[1:]:
        result = (float(value) - result) * multiplier + result
    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        raise ValueError("At least 15 candles are needed for RSI 14.")
    changes = [float(values[index]) - float(values[index - 1]) for index in range(1, len(values))]
    gains = [max(change, 0) for change in changes[-period:]]
    losses = [abs(min(change, 0)) for change in changes[-period:]]
    average_gain, average_loss = sum(gains) / period, sum(losses) / period
    return 100.0 if not average_loss else 100 - (100 / (1 + average_gain / average_loss))


def atr(candles, period=14):
    if len(candles) < period + 1:
        raise ValueError("At least 15 candles are needed for ATR 14.")
    ranges = []
    window = candles[-(period + 1):]
    for index, candle in enumerate(window):
        previous = window[index - 1] if index else candle
        ranges.append(max(float(candle["high"]) - float(candle["low"]), abs(float(candle["high"]) - float(previous["close"])), abs(float(candle["low"]) - float(previous["close"]))))
    return sum(ranges[1:]) / period


def supertrend(candles, period=10, multiplier=3.0):
    if len(candles) < period + 1:
        raise ValueError("More candles are needed to calculate SuperTrend.")
    true_ranges = []
    for index, candle in enumerate(candles):
        high, low = float(candle["high"]), float(candle["low"])
        previous_close = float(candles[index - 1]["close"]) if index else float(candle["close"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    atr = ema(true_ranges, period)
    current = candles[-1]
    mid = (float(current["high"]) + float(current["low"])) / 2
    upper, lower = mid + multiplier * atr, mid - multiplier * atr
    # A clear, reproducible current-band approximation for the fixed TPS profile.
    return lower if float(current["close"]) >= lower else upper


def _current_session_candles(candles):
    try:
        last_day = datetime.fromisoformat(str(candles[-1]["time"])).date()
        return [candle for candle in candles if datetime.fromisoformat(str(candle["time"])).date() == last_day]
    except (ValueError, TypeError, KeyError):
        return candles


def analyse_volume_candle(candles, period=20, heavy_ratio=1.5):
    """Classify the latest traded candle without treating a wick as a breakout.

    A large traded-volume candle is useful only when it closes near the edge of
    its range.  This keeps a high-volume rejection wick from being called a
    reliable buying/selling confirmation.
    """
    if len(candles) < period:
        return {"volume_ratio": None, "volume_signal": "Volume history unavailable", "candle_direction": "NEUTRAL", "fake_breakout_risk": True}
    latest = candles[-1]
    volume = float(latest.get("volume", 0) or 0)
    volume_ema = ema([float(candle.get("volume", 0) or 0) for candle in candles[-period:]], period)
    if volume_ema <= 0:
        return {"volume_ratio": None, "volume_signal": "Traded volume unavailable", "candle_direction": "NEUTRAL", "fake_breakout_risk": True}
    high, low = float(latest["high"]), float(latest["low"])
    opening, close = float(latest["open"]), float(latest["close"])
    candle_range = max(high - low, 0.000001)
    body_ratio = abs(close - opening) / candle_range
    close_position = (close - low) / candle_range
    volume_ratio = volume / volume_ema
    heavy = volume_ratio >= heavy_ratio
    bullish = close > opening
    bearish = close < opening
    bullish_quality = bullish and body_ratio >= 0.55 and close_position >= 0.70
    bearish_quality = bearish and body_ratio >= 0.55 and close_position <= 0.30
    if heavy and bullish_quality:
        signal, fake_risk = "Heavy buying confirmation", False
    elif heavy and bearish_quality:
        signal, fake_risk = "Heavy selling confirmation", False
    elif heavy:
        signal, fake_risk = "High-volume rejection — fake-move risk", True
    else:
        signal, fake_risk = "Volume below heavy-confirmation threshold", True
    return {
        "volume_ratio": volume_ratio, "volume_signal": signal,
        "candle_direction": "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL",
        "candle_body_ratio": body_ratio, "candle_close_position": close_position,
        "fake_breakout_risk": fake_risk,
    }


def build_live_capture(symbol, timeframe, candles, analysis_source="Angel One candle data"):
    """Return fields compatible with Chart Capture and Decision Engine V1."""
    if len(candles) < 51:
        raise ValueError("At least 51 candles are needed for EMA 50 live capture.")
    latest = candles[-1]
    closes = [float(candle["close"]) for candle in candles]
    volumes = [float(candle.get("volume", 0) or 0) for candle in candles]
    session = _current_session_candles(candles)
    session_volume = sum(float(candle.get("volume", 0) or 0) for candle in session)
    if session_volume > 0:
        vwap = sum(
            ((float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3) * float(candle.get("volume", 0) or 0)
            for candle in session
        ) / session_volume
        volume = float(latest.get("volume", 0) or 0)
        volume_ema = ema(volumes[-20:], 20)
        volume_note = f"Volume and VWAP calculated from {analysis_source}."
    else:
        vwap = volume = volume_ema = None
        volume_note = "Angel One returned no index volume; Volume/VWAP are unavailable and must not be guessed."
    trend = supertrend(candles[-60:])
    close = float(latest["close"])
    volume_analysis = analyse_volume_candle(candles)
    number = lambda value: f"{value:.2f}" if value is not None else ""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "open": number(float(latest["open"])), "high": number(float(latest["high"])),
        "low": number(float(latest["low"])), "close": number(close),
        "ema_5": number(ema(closes[-20:], 5)), "ema_20": number(ema(closes[-50:], 20)),
        "ema_50": number(ema(closes[-100:], 50)), "vwap": number(vwap),
        "rsi_14": number(rsi(closes)), "atr_14": number(atr(candles)),
        "supertrend": number(trend),
        "supertrend_state": "Green / Bullish" if close >= trend else "Red / Bearish",
        "volume": number(volume), "volume_ema": number(volume_ema), "volume_ema_period": "20",
        "volume_ratio": number(volume_analysis.get("volume_ratio")),
        "volume_signal": volume_analysis.get("volume_signal"),
        "candle_direction": volume_analysis.get("candle_direction", "NEUTRAL"),
        "candle_body_ratio": number(volume_analysis.get("candle_body_ratio")),
        "candle_close_position": number(volume_analysis.get("candle_close_position")),
        "fake_breakout_risk": bool(volume_analysis.get("fake_breakout_risk", True)),
        "analysis_source": analysis_source,
        "raw_text": f"Angel One live setup capture: {symbol} {timeframe}. {volume_note}",
    }
