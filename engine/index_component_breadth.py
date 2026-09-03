"""Explainable index-component breadth; no single snapshot authorizes a trade."""


def analyze_component_breadth(symbol: str, rows: list[dict], expected: int) -> dict:
    usable = [row for row in rows if row.get("change_percent") is not None]
    positive = sum(float(row["change_percent"]) > 0.05 for row in usable)
    negative = sum(float(row["change_percent"]) < -0.05 for row in usable)
    flat = len(usable) - positive - negative
    coverage = round(100 * len(usable) / max(expected, 1))
    positive_pct = round(100 * positive / max(len(usable), 1), 1)
    negative_pct = round(100 * negative / max(len(usable), 1), 1)
    if coverage < 80:
        state = "DATA GAP"
    elif positive_pct >= 60:
        state = "BULLISH"
    elif negative_pct >= 60:
        state = "BEARISH"
    else:
        state = "MIXED"
    leaders = sorted(usable, key=lambda row: float(row["change_percent"]), reverse=True)[:3]
    laggards = sorted(usable, key=lambda row: float(row["change_percent"]))[:3]
    return {"symbol": symbol, "state": state, "positive": positive, "negative": negative, "flat": flat,
            "positive_pct": positive_pct, "negative_pct": negative_pct, "coverage": coverage,
            "observed": len(usable), "expected": expected, "leaders": leaders, "laggards": laggards,
            "explanation": (f"{symbol}: {positive}/{len(usable)} positive, {negative}/{len(usable)} negative, "
                            f"{flat} flat; coverage {coverage}%. Breadth {state}." )}


def combine_component_breadth(results: list[dict]) -> dict:
    usable = [row for row in results if row.get("state") != "DATA GAP"]
    bullish = sum(row["state"] == "BULLISH" for row in usable)
    bearish = sum(row["state"] == "BEARISH" for row in usable)
    state = "BULLISH" if bullish >= 2 else "BEARISH" if bearish >= 2 else "MIXED" if len(usable) >= 2 else "DATA GAP"
    return {"state": state, "coverage": f"{len(usable)}/3",
            "explanation": " | ".join(row["explanation"] for row in results)}
