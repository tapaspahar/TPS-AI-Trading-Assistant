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


def build_live_capture(symbol, timeframe, candles):
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
        volume_note = "Volume and VWAP calculated from Angel One candle data."
    else:
        vwap = volume = volume_ema = None
        volume_note = "Angel One returned no index volume; Volume/VWAP are unavailable and must not be guessed."
    trend = supertrend(candles[-60:])
    close = float(latest["close"])
    number = lambda value: f"{value:.2f}" if value is not None else ""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "open": number(float(latest["open"])), "high": number(float(latest["high"])),
        "low": number(float(latest["low"])), "close": number(close),
        "ema_5": number(ema(closes[-20:], 5)), "ema_20": number(ema(closes[-50:], 20)),
        "ema_50": number(ema(closes[-100:], 50)), "vwap": number(vwap),
        "supertrend": number(trend),
        "supertrend_state": "Green / Bullish" if close >= trend else "Red / Bearish",
        "volume": number(volume), "volume_ema": number(volume_ema), "volume_ema_period": "20",
        "raw_text": f"Angel One live setup capture: {symbol} {timeframe}. {volume_note}",
    }
