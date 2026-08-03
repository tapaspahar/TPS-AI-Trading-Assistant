"""Transparent Black-Scholes estimates for option review, never order execution."""
from __future__ import annotations

from datetime import date, datetime, time
from math import erf, exp, log, pi, sqrt


def _cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2.0 * pi)


def _price(spot, strike, years, rate, volatility, option_type):
    root_time = sqrt(years)
    d1 = (log(spot / strike) + (rate + volatility * volatility / 2) * years) / (volatility * root_time)
    d2 = d1 - volatility * root_time
    discount = exp(-rate * years)
    if option_type == "CE":
        return spot * _cdf(d1) - strike * discount * _cdf(d2)
    return strike * discount * _cdf(-d2) - spot * _cdf(-d1)


def calculate_greeks(spot, strike, premium, expiry, option_type, now: datetime | None = None, rate: float = 0.065):
    """Return model estimates from a live option premium, or ``None`` when unsafe.

    Angel One quotes do not guarantee an IV/Greeks feed for every contract, so
    these values are labelled estimates and are deliberately withheld for
    invalid, expired or illiquid-looking inputs.
    """
    spot, strike, premium = float(spot), float(strike), float(premium)
    if min(spot, strike, premium) <= 0 or option_type not in {"CE", "PE"}:
        return None
    now = now or datetime.now()
    if isinstance(expiry, datetime):
        expiry_dt = expiry
    elif isinstance(expiry, date):
        expiry_dt = datetime.combine(expiry, time(15, 30))
    else:
        return None
    seconds = (expiry_dt - now).total_seconds()
    if seconds <= 3600:
        return None
    years = seconds / (365.0 * 24 * 60 * 60)
    lower, upper = 0.01, 5.0
    if not (_price(spot, strike, years, rate, lower, option_type) <= premium <= _price(spot, strike, years, rate, upper, option_type)):
        return None
    for _ in range(70):
        volatility = (lower + upper) / 2
        if _price(spot, strike, years, rate, volatility, option_type) > premium:
            upper = volatility
        else:
            lower = volatility
    volatility = (lower + upper) / 2
    root_time = sqrt(years)
    d1 = (log(spot / strike) + (rate + volatility * volatility / 2) * years) / (volatility * root_time)
    d2 = d1 - volatility * root_time
    discount = exp(-rate * years)
    delta = _cdf(d1) if option_type == "CE" else _cdf(d1) - 1
    gamma = _pdf(d1) / (spot * volatility * root_time)
    theta = (-(spot * _pdf(d1) * volatility) / (2 * root_time) - rate * strike * discount * (_cdf(d2) if option_type == "CE" else _cdf(-d2))) / 365
    vega = spot * _pdf(d1) * root_time / 100
    return {
        "iv": round(volatility * 100, 2), "delta": round(delta, 3), "gamma": round(gamma, 5),
        "theta_per_day": round(theta, 2), "vega_per_1pct": round(vega, 2), "days_to_expiry": round(seconds / 86400, 2),
    }
