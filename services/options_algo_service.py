"""Daily options-algo limits and net-after-charge accounting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgoDayState:
    state: str
    reason: str
    gross_pnl: float
    estimated_charges: float
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
    net = round(gross - charges, 2)
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
        state, reason, round(gross, 2), charges, net, trades, opened,
        max(0, limit - trades), allow,
    )
