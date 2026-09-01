"""Expiry 3 PM shadow study inspired by public momentum/risk concepts.

This is an original evidence model, not a copy of a paid or undisclosed rule.
It keeps premium acceleration, participation and opposite-leg behaviour separate
and never authorizes a broker order.
"""
from __future__ import annotations


def evaluate_three_pm_shadow(rows, *, spot_move=0.0, spot_reference=0.0):
    usable = [row for row in rows if float(row.get("premium") or 0) > 0]
    if not usable:
        return {"state": "DATA GAP", "score": 0, "side": "-", "evidence": ["No valid option premiums"]}
    threshold = max(5.0, abs(float(spot_reference or 0)) * .00025)
    direction = "CE" if spot_move >= threshold else "PE" if spot_move <= -threshold else "NEUTRAL"
    scored = []
    for row in usable:
        side = str(row.get("option_type") or "").upper()
        premium_move = float(row.get("premium_change_pct") or 0)
        volume_ratio = row.get("volume_ratio")
        oi_change = row.get("oi_change_pct")
        score, evidence = 0, []
        if premium_move >= 20: score += 30; evidence.append(f"premium acceleration {premium_move:+.1f}%")
        if premium_move >= 40: score += 15; evidence.append("big-bar style premium expansion")
        if volume_ratio is not None and float(volume_ratio) >= 2: score += 25; evidence.append(f"volume {float(volume_ratio):.1f}x")
        if oi_change is not None and abs(float(oi_change)) >= 3: score += 10; evidence.append(f"OI change {float(oi_change):+.1f}%")
        if direction == side: score += 20; evidence.append(f"spot move confirms {side}")
        elif direction != "NEUTRAL": score -= 20; evidence.append("spot/premium conflict")
        if str(row.get("source_completeness") or "").upper() == "COMPLETE": score += 5
        scored.append((score, side, row, evidence))
    score, side, best, evidence = max(scored, key=lambda item: item[0])
    state = "SHADOW CANDIDATE" if score >= 70 else "WATCH" if score >= 45 else "NO SETUP"
    return {
        "state": state, "score": max(0, min(100, int(score))), "side": side,
        "contract": best.get("contract_symbol") or best.get("contract", ""),
        "evidence": evidence,
        "policy": "PAPER/SHADOW ONLY until at least 30 independent expiry observations validate expectancy",
    }
