"""Rank active F&O cash underlyings for deeper TPS research."""

from __future__ import annotations

from math import log10


def rank_fno_universe(universe: list[dict], quotes: list[dict], limit: int = 5) -> list[dict]:
    """Return liquid, moving F&O stocks without treating ranking as a trade signal."""
    by_token = {str(row.get("token")): row for row in universe if row.get("token")}
    ranked = []
    for quote in quotes:
        token = str(quote.get("symbolToken") or quote.get("symboltoken") or quote.get("token") or "")
        equity = by_token.get(token)
        if not equity:
            continue
        ltp = _number(quote, "ltp", "last_traded_price")
        previous = _number(quote, "close", "previousClose", "previous_close")
        volume = _number(quote, "tradeVolume", "volume")
        high = _number(quote, "high", "dayHigh", "day_high")
        low = _number(quote, "low", "dayLow", "day_low")
        change = _number(quote, "percentChange", "percent_change")
        if not change and previous > 0:
            change = (ltp - previous) / previous * 100
        turnover = ltp * volume
        if ltp <= 10 or volume <= 0 or turnover < 5_000_000 or abs(change) > 20:
            continue
        liquidity = max(0.0, min(50.0, (log10(max(turnover, 1)) - 6.0) * 16.67))
        movement = min(30.0, abs(change) / 3.0 * 30.0)
        if high > low > 0:
            range_position = abs((ltp - ((high + low) / 2)) / ((high - low) / 2))
            participation = min(20.0, range_position * 20.0)
        else:
            participation = 0.0
        score = round(liquidity + movement + participation, 1)
        direction = "bullish activity" if change > 0 else "bearish activity" if change < 0 else "active range"
        ranked.append({
            **equity,
            "selection_source": "AUTO F&O DISCOVERY",
            "selection_score": score,
            "selection_reason": (
                f"Auto-selected: {direction}, {change:+.2f}% change, "
                f"volume {volume:,.0f}, turnover Rs {turnover / 10_000_000:.1f} Cr"
            ),
            "quote_ltp": ltp,
            "quote_change_percent": change,
            "quote_volume": volume,
            "quote_turnover": turnover,
        })
    ranked.sort(key=lambda row: (row["selection_score"], row["quote_turnover"]), reverse=True)
    return ranked[:max(1, min(int(limit), 12))]


def _number(row: dict, *names: str) -> float:
    for name in names:
        try:
            value = row.get(name)
            if value not in (None, "", "-"):
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0
