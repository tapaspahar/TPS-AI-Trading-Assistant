"""Daily options-algo limits and net-after-charge accounting."""
from __future__ import annotations

from dataclasses import dataclass
from math import inf


@dataclass(frozen=True)
class AlgoDayState:
    state: str
    reason: str
    gross_pnl: float
    estimated_charges: float
    estimated_slippage: float
    net_pnl: float
    trades: int
    open_trades: int
    remaining_trades: int
    allow_new_entry: bool


def calculate_algo_day_state(progress: dict, settings: dict, *, session_active: bool) -> AlgoDayState:
    """Fail closed when a daily boundary or the explicit session switch is reached."""
    trades = int(progress.get("trades", 0) or 0)
    closed = int(progress.get("closed_trades", 0) or 0)
    opened = int(progress.get("open_trades", 0) or 0)
    gross = float(progress.get("realized_pnl", 0) or 0)
    per_trade_charges = max(0.0, float(settings.get("options_algo_estimated_charges", 0) or 0))
    charges = round(closed * per_trade_charges, 2)
    per_trade_slippage = max(0.0, float(settings.get("options_algo_estimated_slippage", 0) or 0))
    slippage = round(closed * per_trade_slippage, 2)
    net = round(gross - charges - slippage, 2)
    target = max(0.0, float(settings.get("options_algo_daily_target_net", 0) or 0))
    max_loss = max(0.0, float(settings.get("options_algo_daily_max_loss", 0) or 0))
    limit = max(1, min(10, int(settings.get("options_algo_max_trades", 10) or 10)))
    state, reason = "READY", "Daily boundaries available; completed-candle opportunity ka wait hai."
    if target and net >= target:
        state, reason = "TARGET HIT", f"Net daily target ₹{target:,.2f} achieved."
    elif max_loss and net <= -max_loss:
        state, reason = "LOSS LIMIT HIT", f"Net daily maximum loss ₹{max_loss:,.2f} reached."
    elif trades >= limit:
        state, reason = "TRADE LIMIT HIT", f"Daily {limit}-trade limit complete."
    elif not session_active:
        state, reason = "STOPPED", "Start Algo Session tick karke current session activate karein."
    allow = state == "READY" and opened == 0
    if state == "READY" and opened:
        state, reason, allow = "MONITORING OPEN TRADE", "Open option trade target/stop/time-exit monitor ho raha hai.", False
    return AlgoDayState(
        state, reason, round(gross, 2), charges, slippage, net, trades, opened,
        max(0, limit - trades), allow,
    )


@dataclass(frozen=True)
class AlgoValidationMetrics:
    closed_trades: int
    wins: int
    win_rate: float
    expectancy: float
    profit_factor: float | None
    max_drawdown: float
    ready_for_review: bool
    reason: str


def calculate_validation_metrics(rows, settings: dict) -> AlgoValidationMetrics:
    """Calculate auditable paper evidence; this never authorizes a broker order."""
    costs = max(0.0, float(settings.get("options_algo_estimated_charges", 0) or 0))
    costs += max(0.0, float(settings.get("options_algo_estimated_slippage", 0) or 0))
    pnls = []
    for row in rows:
        value = dict(row) if not isinstance(row, dict) else row
        if str(value.get("status", "")).upper() != "CLOSED" or value.get("pnl") is None:
            continue
        pnls.append(float(value["pnl"]) - costs)
    wins = sum(value > 0 for value in pnls)
    win_rate = round((wins / len(pnls) * 100) if pnls else 0.0, 1)
    expectancy = round(sum(pnls) / len(pnls), 2) if pnls else 0.0
    gains, losses = sum(max(0.0, p) for p in pnls), abs(sum(min(0.0, p) for p in pnls))
    profit_factor = None if losses == 0 else round(gains / losses, 2)
    equity = peak = 0.0; max_drawdown = 0.0
    for pnl in reversed(pnls):
        equity += pnl; peak = max(peak, equity); max_drawdown = max(max_drawdown, peak - equity)
    minimum = int(settings.get("options_algo_min_validation_trades", 30) or 30)
    minimum_win = float(settings.get("options_algo_min_validation_win_rate", 55) or 55)
    drawdown_cap = float(settings.get("options_algo_max_validation_drawdown", inf) or inf)
    reasons = []
    if len(pnls) < minimum: reasons.append(f"sample {len(pnls)}/{minimum}")
    if win_rate < minimum_win: reasons.append(f"win rate {win_rate:.1f}% < {minimum_win:.1f}%")
    if max_drawdown > drawdown_cap: reasons.append(f"drawdown ₹{max_drawdown:,.2f} > ₹{drawdown_cap:,.2f}")
    ready = not reasons
    return AlgoValidationMetrics(len(pnls), wins, win_rate, expectancy, profit_factor,
                                 round(max_drawdown, 2), ready,
                                 "Paper evidence review-ready." if ready else "; ".join(reasons))
