"""Planning and KPI summary for the 30-session CE+PE paper experiment."""
from __future__ import annotations

import json
import math


SOURCE_PAGE = "DAILY_CE_PE_FORWARD_TEST"


def build_forward_test_plan(*, ce_price, pe_price, lot_size, capital_limit=100000.0,
                            daily_target_net=2000.0, estimated_costs=100.0,
                            target_move_points=50.0, maximum_loss=2000.0):
    """Size the smallest whole-lot pair whose planned move covers net target."""
    values = (ce_price, pe_price, lot_size, capital_limit, daily_target_net,
              target_move_points, maximum_loss)
    if min(float(value) for value in values) <= 0 or float(estimated_costs) < 0:
        raise ValueError("Positive premiums, lot size, capital, target, target move and maximum loss required hain.")
    gross_target = float(daily_target_net) + float(estimated_costs)
    lots = max(1, math.ceil(gross_target / (float(target_move_points) * int(lot_size))))
    quantity = lots * int(lot_size)
    combined_entry = float(ce_price) + float(pe_price)
    capital_required = combined_entry * quantity
    if capital_required > float(capital_limit):
        raise ValueError(
            f"Planned pair ko ₹{capital_required:,.2f} chahiye, capital ceiling ₹{float(capital_limit):,.2f} hai."
        )
    return {
        "lots": lots, "quantity": quantity, "combined_entry": combined_entry,
        "capital_required": capital_required, "capital_limit": float(capital_limit),
        "daily_target_net": float(daily_target_net), "estimated_costs": float(estimated_costs),
        "target_pnl_gross": gross_target, "target_move_points": gross_target / quantity,
        "target_combined_premium": combined_entry + (gross_target / quantity),
        "maximum_loss": float(maximum_loss),
    }


def summarize_forward_test(rows, required_sessions=30, max_drawdown_limit=10000.0):
    """Summarize closed PAPER sessions; open/failed rows never inflate results."""
    closed = [row for row in rows if str(row["mode"]).upper() == "PAPER"
              and str(row["status"]).upper() == "PAPER_CLOSED"]
    net_results = []
    target_hits = 0
    for row in closed:
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            details = {}
        costs = float(details.get("estimated_costs", 0) or 0)
        net_results.append(float(row["last_pnl"] or 0) - costs)
        target_hits += str(row["exit_reason"] or "").upper() == "COMBINED TARGET HIT"
    equity = peak = drawdown = 0.0
    for result in net_results:
        equity += result; peak = max(peak, equity); drawdown = max(drawdown, peak - equity)
    count = len(closed)
    wins = sum(value > 0 for value in net_results)
    target_rate = (100.0 * target_hits / count) if count else 0.0
    win_rate = (100.0 * wins / count) if count else 0.0
    eligible = (count >= int(required_sessions) and sum(net_results) > 0
                and target_rate >= 70.0 and drawdown <= float(max_drawdown_limit))
    return {
        "closed_sessions": count, "remaining_sessions": max(0, int(required_sessions) - count),
        "target_hits": target_hits, "target_hit_rate": target_rate, "wins": wins,
        "win_rate": win_rate, "net_pnl": sum(net_results),
        "average_net": (sum(net_results) / count) if count else 0.0,
        "max_drawdown": drawdown, "real_review_eligible": eligible,
    }
