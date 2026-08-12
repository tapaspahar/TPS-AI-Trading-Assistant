"""Normalize TPS research engines into one actionable opportunity ledger."""

from __future__ import annotations

from datetime import datetime


def option_opportunity(result: dict, settings: dict) -> dict:
    published = bool(result.get("published"))
    quote = result.get("option_quote") or {}
    side = result.get("candidate")
    entry = float(quote.get("ask") or quote.get("ltp") or 0)
    score = float(result.get("dominant_strength") or 0)
    base = _base("INDEX OPTION", result.get("symbol"), result.get("candle_time"), score)
    if not published or not side or entry <= 0:
        return {**base, "action": "WAIT", "state": "NO PUBLISHED SIGNAL", "instrument": "-",
                "blockers": result.get("blockers") or ["No liquid index-option signal"],
                "evidence": _evidence(result), "entry": None, "stop": None, "target_1": None, "target_2": None,
                "quantity": None, "rr_ratio": None, "exit_rule": "Re-evaluate after next completed 5-minute candle."}
    risk = max(entry * 0.20, 0.05)
    rr = max(1.5, float(settings.get("minimum_rr_ratio", 1.5)))
    return {
        **base, "action": f"BUY {side}", "state": "PAPER RESEARCH CANDIDATE",
        "instrument": quote.get("symbol", "-"), "entry": round(entry, 2),
        "stop": round(entry - risk, 2), "target_1": round(entry + risk * rr, 2),
        "target_2": round(entry + risk * max(2.0, rr + 0.5), 2),
        "quantity": int(quote.get("lot_size") or 0) or None, "rr_ratio": round(rr, 2),
        "blockers": [], "evidence": _evidence(result),
        "exit_rule": f"Exit at stop/targets, opposite Powerful Engine signal, or {int(settings.get('time_exit_minutes_before_close', 10))} minutes before close.",
    }


def stock_option_opportunity(result: dict) -> dict:
    plan = result.get("plan") or {}
    base = _base("STOCK OPTION", result.get("underlying"), (result.get("capture") or {}).get("candle_time"), result.get("score", 0))
    if not plan:
        return {**base, "action": "WAIT", "state": result.get("state", "WATCH"), "instrument": "-",
                "entry": None, "stop": None, "target_1": None, "target_2": None, "quantity": None,
                "rr_ratio": None, "blockers": result.get("blockers") or ["TPS stock-option gates not complete"],
                "evidence": _stock_evidence(result), "exit_rule": "Re-evaluate after next completed 5-minute candle."}
    return {
        **base, "action": f"BUY {plan.get('option_type', result.get('candidate'))}",
        "state": "PAPER RESEARCH CANDIDATE", "instrument": (plan.get("contract") or {}).get("symbol", "-"),
        "entry": float(plan["entry"]), "stop": float(plan["stoploss"]), "target_1": float(plan["target"]),
        "target_2": round(float(plan["entry"]) + 2 * (float(plan["entry"]) - float(plan["stoploss"])), 2),
        "quantity": int(plan.get("quantity") or 0) or None, "rr_ratio": float(plan.get("rr_ratio") or 0),
        "blockers": [], "evidence": list(plan.get("reasons") or []),
        "exit_rule": "Exit at premium stop/targets, opposite underlying structure, liquidity failure, or time exit.",
    }


def equity_opportunity(equity: dict, result: dict, candle_time=None) -> dict:
    score = float(result.get("score") or 0)
    ready = str(result.get("plan_state", "")).startswith("WATCH LONG") and score >= 70
    base = _base("CASH EQUITY", equity.get("symbol"), candle_time, score)
    return {
        **base, "action": "BUY ABOVE" if ready else "WAIT", "state": result.get("plan_state", "WAIT"),
        "instrument": equity.get("symbol", "-"), "entry": float(result["entry"]) if ready else None,
        "stop": float(result["stop_loss"]) if ready else None,
        "target_1": float(result["target_1"]) if ready else None,
        "target_2": float(result["target_2"]) if ready else None,
        "quantity": None,
        "rr_ratio": round((float(result["target_1"]) - float(result["entry"])) / max(float(result["entry"]) - float(result["stop_loss"]), .01), 2) if ready else None,
        "blockers": [] if ready else [result.get("plan_note", "Long setup not ready")],
        "evidence": [item for item in (
            equity.get("selection_reason"), f"Structure {result.get('state')}",
            f"Score {score:.0f}/100", result.get("volume_signal", "Volume unavailable"),
        ) if item],
        "exit_rule": "Enter only after a completed close above trigger with volume; exit at stop, targets, or bearish structure reversal.",
    }


def error_opportunity(market_type, symbol, message):
    return {**_base(market_type, symbol, None, 0), "action": "ERROR", "state": "DATA UNAVAILABLE",
            "instrument": "-", "entry": None, "stop": None, "target_1": None, "target_2": None,
            "quantity": None, "rr_ratio": None, "blockers": [str(message)], "evidence": [],
            "exit_rule": "No suggestion was generated from incomplete data."}


def _base(market_type, symbol, candle_time, score):
    now = datetime.now().astimezone()
    fallback_candle = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    return {"scanned_at": now.isoformat(timespec="seconds"),
            "candle_time": str(candle_time or fallback_candle.isoformat(timespec="seconds")), "market_type": market_type,
            "symbol": str(symbol or "-").upper(), "score": round(float(score or 0), 1)}


def _evidence(result):
    return [f"{item.get('layer')}: {item.get('detail')}" for item in result.get("evidence") or [] if item.get("available")]


def _stock_evidence(result):
    strategy = result.get("strategy") or {}
    return [item for item in (
        result.get("selection_reason"), f"Candidate {result.get('candidate')}",
        f"Score {strategy.get('score', 0)}/100", f"State {result.get('state')}",
    ) if item]
