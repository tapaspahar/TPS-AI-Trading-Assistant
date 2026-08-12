"""Classify price around chart support/resistance without issuing a trade call."""


def classify_level_proximity(price, support, resistance):
    price, support, resistance = float(price), float(support), float(resistance)
    if price <= 0 or support <= 0 or resistance <= 0 or support >= resistance:
        return {"state": "UNAVAILABLE", "tolerance": 0.0, "level": None, "distance": None}
    width = resistance - support
    tolerance = max(price * 0.0005, width * 0.08, 1.0)
    if price < support - tolerance:
        state, level = "BELOW_SUPPORT", support
    elif abs(price - support) <= tolerance:
        state, level = "SUPPORT_ZONE", support
    elif price > resistance + tolerance:
        state, level = "ABOVE_RESISTANCE", resistance
    elif abs(price - resistance) <= tolerance:
        state, level = "RESISTANCE_ZONE", resistance
    else:
        state, level = "MID_RANGE", None
    return {
        "state": state, "tolerance": tolerance, "level": level,
        "distance": abs(price - level) if level is not None else None,
    }
