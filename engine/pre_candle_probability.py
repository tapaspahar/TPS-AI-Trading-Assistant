"""Leakage-safe next-candle probability research engine.

The engine compares the latest completed-candle "DNA" with historical analogs.
It never uses a future candle while building the feature vector and only
publishes a directional signal after walk-forward purity clears the configured
gate.  This is research evidence, not a promise that the next candle will move
as predicted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import cos, exp, pi, sin, sqrt


LABELS = ("BULLISH", "BEARISH", "RANGE")
MIN_FEATURE_CANDLES = 55


def _clip(value, low=-4.0, high=4.0):
    return max(low, min(high, float(value)))


def _ema(values, period):
    multiplier = 2.0 / (period + 1.0)
    result = float(values[0])
    for value in values[1:]:
        result += (float(value) - result) * multiplier
    return result


def _atr(rows, period=14):
    window = rows[-(period + 1):]
    ranges = []
    for index in range(1, len(window)):
        current, previous = window[index], window[index - 1]
        ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    return max(sum(ranges) / max(len(ranges), 1), 1e-9)


def _normalise(candles):
    rows = []
    for candle in candles:
        try:
            rows.append({
                "time": str(candle.get("time", "")),
                "open": float(candle["open"]), "high": float(candle["high"]),
                "low": float(candle["low"]), "close": float(candle["close"]),
                "volume": float(candle.get("volume", 0) or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def _clock_features(stamp):
    try:
        moment = datetime.fromisoformat(str(stamp))
        minute = moment.hour * 60 + moment.minute
        phase = 2 * pi * minute / (24 * 60)
        return sin(phase), cos(phase)
    except (TypeError, ValueError):
        return 0.0, 0.0


def _feature(rows, end):
    history = rows[:end + 1]
    if len(history) < MIN_FEATURE_CANDLES:
        raise ValueError("At least 55 completed candles are required.")
    latest = history[-1]
    closes = [row["close"] for row in history]
    volumes = [row["volume"] for row in history]
    atr = _atr(history)
    candle_range = max(latest["high"] - latest["low"], 1e-9)
    body = latest["close"] - latest["open"]
    upper_wick = latest["high"] - max(latest["open"], latest["close"])
    lower_wick = min(latest["open"], latest["close"]) - latest["low"]
    ema5, ema20, ema50 = _ema(closes[-20:], 5), _ema(closes[-50:], 20), _ema(closes[-55:], 50)
    prior_ema5 = _ema(closes[-21:-1], 5)
    volume_mean = sum(volumes[-20:]) / 20 if any(volumes[-20:]) else 0.0
    recent_ranges = [max(row["high"] - row["low"], 1e-9) for row in history[-20:]]
    short_range = sum(recent_ranges[-5:]) / 5
    long_range = sum(recent_ranges) / 20
    streak = 0
    for index in range(len(closes) - 1, max(len(closes) - 7, 0), -1):
        change = closes[index] - closes[index - 1]
        direction = 1 if change > 0 else -1 if change < 0 else 0
        if not streak or (streak > 0 and direction > 0) or (streak < 0 and direction < 0):
            streak += direction
        else:
            break
    clock_sin, clock_cos = _clock_features(latest["time"])
    vector = (
        _clip((closes[-1] - closes[-2]) / atr),
        _clip((closes[-1] - closes[-4]) / atr),
        _clip((closes[-1] - closes[-7]) / atr),
        _clip(body / candle_range, -1, 1),
        _clip(upper_wick / candle_range, 0, 1),
        _clip(lower_wick / candle_range, 0, 1),
        _clip(candle_range / atr, 0, 4),
        _clip((latest["close"] - ema5) / atr),
        _clip((ema5 - ema20) / atr),
        _clip((ema20 - ema50) / atr),
        _clip((ema5 - prior_ema5) / atr),
        _clip(latest["volume"] / volume_mean if volume_mean else 1.0, 0, 4),
        _clip(short_range / long_range if long_range else 1.0, 0, 4),
        _clip(streak / 6.0, -1, 1),
        clock_sin, clock_cos,
    )
    regime = (
        1 if ema5 > ema20 else -1,
        1 if ema20 > ema50 else -1,
        1 if latest["close"] > ema20 else -1,
    )
    return vector, regime, atr


def _outcome(rows, end, atr, range_threshold=0.10):
    delta = rows[end + 1]["close"] - rows[end]["close"]
    normalised = delta / atr
    if normalised > range_threshold:
        return "BULLISH", normalised
    if normalised < -range_threshold:
        return "BEARISH", normalised
    return "RANGE", normalised


@dataclass(frozen=True)
class _Sample:
    vector: tuple
    regime: tuple
    label: str
    move_atr: float


def _distance(left, right):
    # Trend/price features receive slightly more influence than clock context.
    weights = (1.4, 1.2, 1.0, 0.9, 0.5, 0.5, 0.8, 1.2, 1.4, 1.4, 0.9, 0.6, 0.6, 0.5, 0.15, 0.15)
    return sqrt(sum(weight * (a - b) ** 2 for weight, a, b in zip(weights, left, right)))


def _predict(vector, regime, samples):
    if len(samples) < 25:
        return None
    ranked = []
    for sample in samples:
        distance = _distance(vector, sample.vector)
        regime_matches = sum(a == b for a, b in zip(regime, sample.regime))
        weight = exp(-0.75 * distance) * (0.70 + 0.15 * regime_matches)
        ranked.append((distance, weight, sample))
    neighbor_count = min(31, max(15, int(sqrt(len(samples)) * 2)))
    neighbors = sorted(ranked, key=lambda item: item[0])[:neighbor_count]
    votes = {label: 1.0 for label in LABELS}  # Laplace smoothing
    for _distance_value, weight, sample in neighbors:
        votes[sample.label] += weight
    total = sum(votes.values())
    probabilities = {label: votes[label] / total for label in LABELS}
    label = max(LABELS, key=lambda item: probabilities[item])
    selected = [(weight, sample.move_atr) for _distance_value, weight, sample in neighbors if sample.label == label]
    move_atr = sum(weight * move for weight, move in selected) / max(sum(weight for weight, _move in selected), 1e-9)
    return {
        "label": label, "probabilities": probabilities, "confidence": probabilities[label],
        "move_atr": move_atr, "neighbors": neighbor_count,
        "average_distance": sum(item[0] for item in neighbors) / len(neighbors),
    }


def analyze_pre_candle_probability(candles, minimum_purity=60):
    """Return current prediction plus honest expanding-window validation."""
    minimum_purity = max(50, min(95, int(minimum_purity)))
    rows = _normalise(candles)
    if len(rows) < 140:
        raise ValueError("At least 140 valid completed candles are required for prediction and walk-forward validation.")

    samples = []
    validations = []
    gate = minimum_purity / 100.0
    for end in range(MIN_FEATURE_CANDLES - 1, len(rows) - 1):
        vector, regime, atr = _feature(rows, end)
        label, move_atr = _outcome(rows, end, atr)
        prediction = _predict(vector, regime, samples)
        if prediction and prediction["label"] != "RANGE" and prediction["confidence"] >= gate:
            validations.append((prediction["label"], label, prediction["confidence"]))
        samples.append(_Sample(vector, regime, label, move_atr))

    current_vector, current_regime, current_atr = _feature(rows, len(rows) - 1)
    current = _predict(current_vector, current_regime, samples)
    if not current:
        raise ValueError("Historical analog sample is insufficient for a current prediction.")
    correct = sum(predicted == actual for predicted, actual, _confidence in validations)
    validation_count = len(validations)
    purity = (correct / validation_count * 100.0) if validation_count else 0.0
    enough_validation = validation_count >= 15
    directional = current["label"] in ("BULLISH", "BEARISH")
    publish = directional and current["confidence"] >= gate and enough_validation and purity >= minimum_purity
    if publish:
        state = f"{current['label']} PROBABILITY SIGNAL"
    elif not enough_validation:
        state = "WAIT - PURITY SAMPLE INSUFFICIENT"
    elif purity < minimum_purity:
        state = "WAIT - VALIDATED PURITY BELOW GATE"
    elif not directional:
        state = "WAIT - RANGE PROBABILITY DOMINANT"
    else:
        state = "WAIT - CURRENT CONFIDENCE BELOW GATE"

    probabilities = {key: value * 100.0 for key, value in current["probabilities"].items()}
    expected_points = current["move_atr"] * current_atr
    return {
        "signal": state,
        "prediction": current["label"],
        "bullish_probability": probabilities["BULLISH"],
        "bearish_probability": probabilities["BEARISH"],
        "range_probability": probabilities["RANGE"],
        "confidence": current["confidence"] * 100.0,
        "expected_move_points": expected_points,
        "expected_move_atr": current["move_atr"],
        "minimum_purity": minimum_purity,
        "validated_purity": purity,
        "validation_signals": validation_count,
        "validation_correct": correct,
        "validation_ready": enough_validation,
        "published": publish,
        "historical_analogs": len(samples),
        "nearest_analogs": current["neighbors"],
        "analog_distance": current["average_distance"],
        "last_candle_time": rows[-1]["time"],
        "last_close": rows[-1]["close"],
        "atr": current_atr,
        "method": "Candle DNA + regime-matched analog consensus + expanding walk-forward purity gate",
        "warning": "Experimental probability research only. Purity is historical out-of-sample classification accuracy, not a profit or future-accuracy guarantee.",
    }
