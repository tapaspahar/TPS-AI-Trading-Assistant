"""Closing Auction Session impact analysis from completed cash/future candles.

Angel One's retail candle feed does not expose the exchange CAS imbalance or
every indicative equilibrium-price update.  This engine therefore labels its
3:00-3:15 VWAP as an OHLCV approximation and never fabricates auction fields.
"""
from __future__ import annotations

from datetime import datetime, time

from engine.live_setup_capture import atr


def _stamp(candle):
    return datetime.fromisoformat(str(candle["time"]))


def _latest_session(candles):
    if not candles:
        raise ValueError("No completed candles are available.")
    latest_day = _stamp(candles[-1]).date()
    return [candle for candle in candles if _stamp(candle).date() == latest_day]


def _approx_vwap(candles):
    volume = sum(float(candle.get("volume", 0) or 0) for candle in candles)
    if volume <= 0:
        raise ValueError("Traded volume is unavailable for the CAS reference window.")
    return sum(
        ((float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3)
        * float(candle.get("volume", 0) or 0)
        for candle in candles
    ) / volume


def analyze_cas_session(cash_candles, future_candles):
    cash_session = _latest_session(cash_candles)
    future_session = _latest_session(future_candles)
    reference_cash = [c for c in cash_session if time(15, 0) <= _stamp(c).time() < time(15, 15)]
    reference_future = [c for c in future_session if time(15, 0) <= _stamp(c).time() < time(15, 15)]
    if len(reference_cash) < 2 or len(reference_future) < 2:
        raise ValueError("3:00-3:15 PM completed cash/future candles are required for CAS analysis.")

    cash_reference = _approx_vwap(reference_cash)
    future_reference = _approx_vwap(reference_future)
    cash_close = float(cash_session[-1]["close"])
    future_close = float(future_session[-1]["close"])
    cash_atr = atr(cash_candles)
    impact = cash_close - cash_reference
    impact_percent = impact / cash_reference * 100
    impact_atr = impact / max(cash_atr, .01)
    future_move = future_close - future_reference
    threshold = max(cash_atr * .10, cash_reference * .0005)
    pressure = "BULLISH CLOSING DEMAND" if impact > threshold else "BEARISH CLOSING SUPPLY" if impact < -threshold else "BALANCED / PINNED CLOSE"
    direction = 1 if impact > threshold else -1 if impact < -threshold else 0
    future_direction = 1 if future_move > threshold else -1 if future_move < -threshold else 0
    agreement = direction != 0 and direction == future_direction
    confidence = 40 + (20 if abs(impact_atr) >= .15 else 0) + (20 if agreement else 0)
    if direction == 0:
        confidence = 45
    session_final = _stamp(cash_session[-1]).time() >= time(15, 25)
    return {
        "trade_date": _stamp(cash_session[-1]).date().isoformat(),
        "cash_reference": round(cash_reference, 2), "cas_close": round(cash_close, 2),
        "impact_points": round(impact, 2), "impact_percent": round(impact_percent, 3),
        "impact_atr": round(impact_atr, 2), "future_reference": round(future_reference, 2),
        "future_close": round(future_close, 2), "future_move": round(future_move, 2),
        "closing_basis": round(future_close - cash_close, 2), "pressure": pressure,
        "future_agreement": agreement, "confidence": min(confidence, 85),
        "session_final": session_final,
        "cash_last_candle": str(cash_session[-1]["time"]), "future_last_candle": str(future_session[-1]["time"]),
        "warning": (
            "Research estimate only: reference VWAP is approximated from Angel One 5-minute OHLCV. "
            "Exchange IEP, cumulative buy/sell quantity and imbalance are unavailable and are not guessed."
        ),
    }
