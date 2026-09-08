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
    explanations = []
    for row in results:
        explanation = str(row.get("explanation") or "").strip()
        if not explanation:
            symbol = str(row.get("symbol") or "INDEX")
            row_state = str(row.get("state") or "DATA GAP")
            observed = row.get("observed", 0)
            expected = row.get("expected", 0)
            explanation = f"{symbol}: breadth {row_state}; coverage {observed}/{expected}."
        explanations.append(explanation)
    return {"state": state, "coverage": f"{len(usable)}/3",
            "explanation": " | ".join(explanations)}


def combine_market_evidence(breadth_rows: list[dict], candle_rows: list[dict]) -> dict:
    """Combine latest component, chart and OI reads without inventing missing votes."""
    breadth_by_symbol = {str(row.get("symbol") or "").upper(): row for row in breadth_rows}
    candle_by_symbol = {str(row.get("symbol") or "").upper(): row for row in candle_rows}
    indexes = []
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        breadth = breadth_by_symbol.get(symbol) or {}
        candle = candle_by_symbol.get(symbol) or {}
        component = str(breadth.get("state") or "DATA GAP").upper()
        chart = str(candle.get("direction") or "DATA GAP").upper()
        oi_text = str(candle.get("oi_direction") or "DATA GAP").upper()
        oi_quality = int(candle.get("oi_quality") or 0)
        oi = (
            "BULLISH" if oi_quality >= 60 and "BULLISH" in oi_text
            else "BEARISH" if oi_quality >= 60 and "BEARISH" in oi_text
            else "MIXED" if oi_quality >= 60 and "BALANCED" in oi_text
            else "DATA GAP"
        )
        votes = [value for value in (component, chart, oi) if value in {"BULLISH", "BEARISH"}]
        bulls, bears = votes.count("BULLISH"), votes.count("BEARISH")
        direction = "BULLISH" if bulls >= 2 else "BEARISH" if bears >= 2 else "MIXED / UNCONFIRMED"
        timestamps = [
            str(value) for value in (breadth.get("captured_at"), candle.get("candle_time")) if value
        ]
        indexes.append({
            "symbol": symbol, "direction": direction, "component": component,
            "chart": chart, "oi": oi, "oi_quality": oi_quality,
            "evidence_votes": len(votes), "last_evidence_at": max(timestamps) if timestamps else None,
        })
    bullish = sum(row["direction"] == "BULLISH" for row in indexes)
    bearish = sum(row["direction"] == "BEARISH" for row in indexes)
    final = "BULLISH" if bullish >= 2 else "BEARISH" if bearish >= 2 else "MIXED / WAIT"
    confirmed = sum(row["direction"] in {"BULLISH", "BEARISH"} for row in indexes)
    latest = max((row["last_evidence_at"] for row in indexes if row["last_evidence_at"]), default=None)
    return {"direction": final, "confirmed_indexes": confirmed, "indexes": indexes, "last_evidence_at": latest}
