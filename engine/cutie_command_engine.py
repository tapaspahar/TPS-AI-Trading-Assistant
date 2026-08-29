"""Deterministic, allow-listed natural-language commands for TPS automation.

This is intentionally not an unrestricted trading agent.  A prompt becomes a
small typed intent and can never override broker, risk, market-session, data,
daily-loss or kill-switch controls.
"""
from __future__ import annotations

import re


def _amount(text: str, patterns: tuple[str, ...]):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def parse_cutie_command(prompt: str) -> dict:
    text = " ".join(str(prompt or "").strip().split())
    lower = text.lower()
    if not text:
        raise ValueError("Command likhiye; blank prompt execute nahi ho sakta.")
    if any(word in lower for word in ("bypass", "ignore risk", "without stop", "no stop", "disable kill")):
        raise ValueError("Risk, stop ya kill-switch bypass command allowed nahi hai.")
    if any(word in lower for word in ("kill switch", "emergency stop", "stop algo", "algo band")):
        return {"intent": "STOP_ALGO", "summary": "Options algo ki new entries stop karein."}
    if "status" in lower or "kya chal" in lower:
        return {"intent": "ALGO_STATUS", "summary": "Current algo mode, limits aur validation status dikhayein."}

    start = any(word in lower for word in ("start", "chalu", "activate", "run"))
    algo = "algo" in lower or "automatic" in lower or "automation" in lower
    if start and algo:
        symbol = next((name for name in ("BANKNIFTY", "SENSEX", "NIFTY") if name.lower() in lower), None)
        if not symbol:
            raise ValueError("Index missing hai: NIFTY, BANKNIFTY ya SENSEX mention karein.")
        mode = "REAL" if "real" in lower else "PAPER" if "paper" in lower else None
        if not mode:
            raise ValueError("PAPER ya REAL mode clearly mention karein.")
        target = _amount(text, (r"(?:target|profit)\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",))
        loss = _amount(text, (r"(?:max(?:imum)?\s*)?(?:loss|stop)\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",))
        trades = _amount(text, (r"(?:max(?:imum)?\s*)?([\d]+)\s*trades?", r"trades?\s*([\d]+)"))
        lots = _amount(text, (r"([\d]+)\s*lots?", r"lots?\s*([\d]+)"))
        missing = [name for name, value in (("target", target), ("maximum loss", loss), ("trade limit", trades), ("lots", lots)) if value is None]
        if missing:
            raise ValueError("Command incomplete hai: " + ", ".join(missing) + " mention karein.")
        if target <= 0 or loss <= 0 or not 1 <= trades <= 10 or not 1 <= lots <= 100:
            raise ValueError("Target/loss positive, trades 1–10 aur lots 1–100 hone chahiye.")
        return {
            "intent": "START_ALGO", "mode": mode, "symbol": symbol,
            "target": target, "max_loss": loss, "max_trades": int(trades), "lots": int(lots),
            "summary": f"{symbol} {mode} algo | target ₹{target:,.2f} | max loss ₹{loss:,.2f} | {int(trades)} trades | {int(lots)} lot(s)",
        }
    raise ValueError("Command samajh nahi aayi. Supported: start PAPER algo, algo status, ya kill switch.")
