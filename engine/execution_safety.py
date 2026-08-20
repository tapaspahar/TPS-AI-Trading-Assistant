"""Operational hard blockers applied after evidence scoring."""
from __future__ import annotations

from datetime import datetime, timedelta

from core.market_session import IST, market_session, parse_session_times


def _quote_number(quote, *names):
    for name in names:
        value = quote.get(name)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0


def assess_execution_safety(*, now, candle_time, quote, plan, settings, progress, cooldown_remaining=0,
                            event_risk=None, expiry_day=False, recovery_assessment=None):
    now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    blockers, warnings = [], []
    session = market_session(now, settings)
    if session["state"] != "OPEN":
        blockers.append(f"Trading window is {session['state'].lower()}")
    close_at = datetime.combine(now.date(), parse_session_times(settings)[2], IST)
    minutes_to_close = (close_at - now).total_seconds() / 60
    if minutes_to_close <= int(settings.get("time_exit_minutes_before_close", 10)):
        blockers.append(f"Fresh entry blocked {max(0, round(minutes_to_close))} minutes before market close")
    try:
        candle_at = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00"))
        if candle_at.tzinfo is None:
            candle_at = candle_at.replace(tzinfo=IST)
        age = (now - candle_at.astimezone(IST)).total_seconds() / 60
        if age > 12:
            blockers.append(f"Candle data is stale ({age:.1f} minutes old)")
    except (TypeError, ValueError):
        blockers.append("Candle timestamp is missing or invalid")
    ltp = _quote_number(quote, "ltp")
    volume = _quote_number(quote, "volume", "tradeVolume")
    bid = _quote_number(quote, "bestBidPrice", "bestFiveBuyPrice", "bid")
    ask = _quote_number(quote, "bestAskPrice", "bestFiveSellPrice", "ask")
    if ltp <= 0:
        blockers.append("Selected option quote is invalid")
    if volume < float(settings.get("minimum_option_volume", 100)):
        blockers.append(f"Option volume {volume:.0f} is below minimum {settings.get('minimum_option_volume', 100):.0f}")
    spread_percent = None
    if bid > 0 and ask >= bid:
        spread_percent = (ask - bid) / max((ask + bid) / 2, .01) * 100
        if spread_percent > float(settings.get("maximum_option_spread_percent", 8)):
            blockers.append(f"Bid/ask spread {spread_percent:.1f}% exceeds {settings.get('maximum_option_spread_percent', 8):.1f}%")
    else:
        warnings.append("Bid/ask depth unavailable; LTP and volume were validated")
    risk = float(plan["entry"]) - float(plan["stoploss"])
    reward = float(plan["target"]) - float(plan["entry"])
    rr = reward / risk if risk > 0 else 0
    if rr < float(settings.get("minimum_rr_ratio", 1.5)):
        blockers.append(f"Risk:reward {rr:.2f} is below minimum {settings.get('minimum_rr_ratio', 1.5):.2f}")
    if not plan.get("risk_within_cap", False):
        blockers.append("Planned quantity exceeds the configured per-trade risk cap")
    if progress.get("open_trades"):
        blockers.append("An open paper trade is already being monitored")
    if progress.get("trades", 0) >= int(settings["max_trades_per_day"]):
        blockers.append(f"Daily trade limit reached ({progress['trades']}/{settings['max_trades_per_day']})")
    if progress.get("daily_remaining", 1) <= 0:
        blockers.append("Daily loss limit is exhausted")
    if cooldown_remaining > 0:
        blockers.append(f"Paper-trade cooldown active for {cooldown_remaining} more minute(s)")
    if recovery_assessment and not recovery_assessment.get("allowed", False):
        blockers.extend(recovery_assessment.get("blockers") or ["Recovery Mode blocked this capture"])
    if recovery_assessment:
        warnings.extend(recovery_assessment.get("warnings") or [])
    if settings.get("news_risk_pause"):
        blockers.append("Emergency News Risk Pause is ON")
    if event_risk and event_risk.get("blocked") and not settings.get("event_risk_override"):
        names = ", ".join(item["name"] for item in event_risk.get("high_impact_events", [])[:3])
        blockers.append(f"High-impact economic event window: {names or 'event detected'}")
    if event_risk and not event_risk.get("available") and settings.get("event_feed_fail_closed"):
        blockers.append("Economic-calendar feed unavailable and fail-closed mode is enabled")
    if expiry_day:
        warnings.append("Expiry-day execution requires reduced size and ATM/ITM preference")
    if event_risk and event_risk.get("blocked") and settings.get("event_risk_override"):
        warnings.append("High-impact event block explicitly overridden for paper testing; reduced confidence/risk remains active")
    return {"allowed": not blockers, "blockers": blockers, "warnings": warnings,
            "spread_percent": round(spread_percent, 2) if spread_percent is not None else None, "rr_ratio": round(rr, 2)}
