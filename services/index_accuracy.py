"""Measured auto-paper performance kept separate for each index.

Accuracy is derived only from closed captured paper trades.  Attempt scores are
evidence bands, not probabilities, and remain in learning state until enough
independent closed samples exist.
"""
from __future__ import annotations

from collections import defaultdict

from engine.performance_calibration import calibrate_outcomes


INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")


def index_accuracy_profiles(database, trade_date: str | None = None) -> dict[str, dict]:
    where, values = "", []
    if trade_date:
        where, values = "WHERE a.trade_date=?", [trade_date]
    rows = database.cursor.execute(
        f"""SELECT a.symbol, a.outcome, a.score, a.trade_id,
                   t.status trade_status, t.outcome trade_outcome, t.pnl
            FROM auto_trade_attempts a
            LEFT JOIN trades t ON t.id=a.trade_id
            {where}
            ORDER BY a.checked_at, a.id""",
        values,
    ).fetchall()
    grouped = {symbol: [] for symbol in INDEX_SYMBOLS}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        if symbol in grouped:
            grouped[symbol].append(row)

    profiles = {}
    for symbol, attempts in grouped.items():
        captured = [row for row in attempts if str(row["outcome"] or "").upper() == "CAPTURED"]
        closed = [row for row in captured if str(row["trade_status"] or "").upper() == "CLOSED"]
        pnls = [float(row["pnl"] or 0) for row in closed]
        metrics = calibrate_outcomes(pnls)
        score_groups = defaultdict(list)
        for row in closed:
            if row["score"] is not None:
                lower = min(90, max(0, int(float(row["score"])) // 10 * 10))
                score_groups[lower].append(float(row["pnl"] or 0))
        observed = []
        for lower, band_pnls in score_groups.items():
            band = calibrate_outcomes(band_pnls)
            observed.append((band["expectancy"], band["wilson_lower_bound"], band["samples"], lower))
        best_band = max(observed, default=None)
        confidence = (
            "VALIDATED" if metrics["samples"] >= 30 and metrics["expectancy"] > 0
            and metrics["profit_factor"] >= 1.2 and metrics["wilson_lower_bound"] >= 55
            else "LEARNING" if metrics["samples"] >= 10 else "LOW SAMPLE"
        )
        profiles[symbol] = {
            "symbol": symbol, "attempts": len(attempts), "captured": len(captured),
            "open": len(captured) - len(closed), "closed": len(closed), **metrics,
            "confidence": confidence,
            "best_observed_score_band": (
                f"{best_band[3]}-{100 if best_band[3] == 90 else best_band[3] + 9}"
                if best_band and best_band[2] >= 5 else "INSUFFICIENT SAMPLE"
            ),
        }
    return profiles
