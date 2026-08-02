"""Transparent, rules-based decision support for the fixed TPS chart profile."""

from dataclasses import dataclass

from engine.psychology_engine import PsychologyEngine


@dataclass(frozen=True)
class ChartSnapshot:
    price: float
    ema_5: float
    ema_20: float
    ema_50: float
    vwap: float
    supertrend: float
    volume: float
    volume_ema: float


class DecisionEngine:
    """Scores confirmed chart inputs; it does not send orders or predict prices."""

    def evaluate(self, snapshot: ChartSnapshot, option_type: str, psychology: str = "Calm") -> dict:
        score, reasons, warnings = 0, [], []
        bullish = snapshot.price > snapshot.supertrend
        direction = "BULLISH" if bullish else "BEARISH"

        ema_bullish = snapshot.ema_5 > snapshot.ema_20 > snapshot.ema_50
        ema_bearish = snapshot.ema_5 < snapshot.ema_20 < snapshot.ema_50
        if (bullish and ema_bullish) or (not bullish and ema_bearish):
            score += 25
            reasons.append("EMA 5 / 20 / 50 aligned with trend")
        else:
            warnings.append("EMA alignment does not confirm the trend")

        above_vwap = snapshot.price > snapshot.vwap
        if above_vwap == bullish:
            score += 20
            reasons.append("Price is on the confirming side of VWAP")
        else:
            warnings.append("VWAP does not confirm the trend")

        score += 20
        reasons.append(f"SuperTrend is {direction.lower()}")

        if snapshot.volume > snapshot.volume_ema:
            score += 15
            reasons.append("Volume is above Volume EMA 20")
        else:
            warnings.append("Volume is not above Volume EMA 20")

        option_type = option_type.upper()
        expected_option = "CE" if bullish else "PE"
        if option_type == expected_option:
            score += 10
            reasons.append(f"{option_type} matches {direction.lower()} direction")
        else:
            warnings.append(f"{option_type or 'Option'} conflicts with {direction.lower()} direction; expected {expected_option}")

        psychology_score = PsychologyEngine().evaluate(psychology)
        score += psychology_score
        if psychology_score < 5:
            warnings.append(f"Psychology check: {psychology.title()}")

        score = min(score, 100)
        if score >= 85 and not warnings:
            decision = f"STRONG {expected_option} SETUP"
        elif score >= 65:
            decision = f"WATCH {expected_option}"
        else:
            decision = "NO TRADE"
        return {"score": score, "direction": direction, "decision": decision, "reasons": reasons, "warnings": warnings}
