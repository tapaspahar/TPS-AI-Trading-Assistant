"""Evidence-based calibration for paper-trading outcomes.

Model payoff coverage is deliberately kept separate from observed probability.
Only closed paper outcomes can promote a strategy to a validated tier.
"""

from math import sqrt


def wilson_lower_bound(wins: int, samples: int, z: float = 1.96) -> float:
    if samples <= 0:
        return 0.0
    p = wins / samples
    denominator = 1 + (z * z / samples)
    centre = p + (z * z / (2 * samples))
    margin = z * sqrt((p * (1 - p) / samples) + (z * z / (4 * samples * samples)))
    return 100.0 * (centre - margin) / denominator


def calibrate_outcomes(pnls, minimum_samples: int = 30, target_win_rate: float = 70.0) -> dict:
    values = [float(value or 0) for value in pnls]
    samples = len(values)
    wins = sum(value > 0 for value in values)
    losses = samples - wins
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    average_win = gross_profit / wins if wins else 0.0
    average_loss = gross_loss / losses if losses else 0.0
    win_rate = 100.0 * wins / samples if samples else 0.0
    expectancy = sum(values) / samples if samples else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
    lower_bound = wilson_lower_bound(wins, samples)
    running = peak = max_drawdown = 0.0
    for value in values:
        running += value
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)

    if samples == 0:
        tier = "UNPROVEN"
        reason = "No closed paper outcomes yet"
    elif expectancy <= 0 or profit_factor < 1.0:
        tier = "REJECTED BY EVIDENCE"
        reason = "Observed expectancy/profit factor is not positive"
    elif samples < minimum_samples:
        tier = "PAPER VALIDATION"
        reason = f"Need {minimum_samples - samples} more closed outcomes"
    elif win_rate >= target_win_rate and lower_bound >= 55.0 and profit_factor >= 1.20:
        tier = "VALIDATED LOW-RISK"
        reason = "Sample, win-rate, confidence bound and expectancy gates passed"
    else:
        tier = "PAPER ONLY"
        reason = "70% measured target or confidence gate is not proven"

    return {
        "samples": samples, "wins": wins, "losses": losses,
        "win_rate": round(win_rate, 2), "expectancy": round(expectancy, 2),
        "average_win": round(average_win, 2), "average_loss": round(average_loss, 2),
        "total_pnl": round(sum(values), 2), "profit_factor": round(profit_factor, 2),
        "wilson_lower_bound": round(lower_bound, 2), "validation_tier": tier,
        "max_drawdown": round(max_drawdown, 2),
        "validation_reason": reason, "minimum_samples": minimum_samples,
        "target_win_rate": target_win_rate,
    }
