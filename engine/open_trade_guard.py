"""Conservative reversal warnings for an already-recorded open option trade."""
from __future__ import annotations


def evaluate_open_trade(trade, snapshot_5m, snapshot_15m):
    """Return a review warning only when both timeframes oppose the open option."""
    option = str(trade["option_type"]).upper()
    if option not in {"CE", "PE"}:
        return None

    def bearish(snapshot):
        return (
            float(snapshot["close"]) < float(snapshot["ema_20"])
            and float(snapshot["close"]) < float(snapshot["supertrend"])
            and float(snapshot["rsi_14"] or 50) < 45
        )

    def bullish(snapshot):
        return (
            float(snapshot["close"]) > float(snapshot["ema_20"])
            and float(snapshot["close"]) > float(snapshot["supertrend"])
            and float(snapshot["rsi_14"] or 50) > 55
        )

    reversal = bearish(snapshot_5m) and bearish(snapshot_15m) if option == "CE" else bullish(snapshot_5m) and bullish(snapshot_15m)
    if not reversal:
        return None
    opposite = "bearish" if option == "CE" else "bullish"
    return {
        "trade_id": int(trade["id"]),
        "alert_type": f"{option}_REVERSAL",
        "title": f"Open {option} trade: confirmed {opposite} reversal",
        "message": (
            f"Both 5m and 15m snapshots now show {opposite} structure against this {option} trade. "
            "Review the live option premium and exit risk in Angel One. TPS has not placed or closed any order. "
            "Do not create an opposite plan until this trade is closed and a fresh chart/OI review is complete."
        ),
    }
