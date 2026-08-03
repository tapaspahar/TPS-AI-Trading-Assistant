"""Transparent, rules-based decision support for the fixed TPS chart profile."""

from dataclasses import dataclass

from engine.psychology_engine import PsychologyEngine


@dataclass(frozen=True)
class ChartSnapshot:
    price: float
    ema_5: float
    ema_20: float
    ema_50: float
    vwap: float | None
    supertrend: float
    volume: float | None
    volume_ema: float | None
    rsi_14: float | None = None
    atr_14: float | None = None


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

        if snapshot.vwap is None:
            warnings.append("VWAP is unavailable from the current data source")
        else:
            above_vwap = snapshot.price > snapshot.vwap
            if above_vwap == bullish:
                score += 20
                reasons.append("Price is on the confirming side of VWAP")
            else:
                warnings.append("VWAP does not confirm the trend")

        score += 20
        reasons.append(f"SuperTrend is {direction.lower()}")

        volume_confirmed = False
        if snapshot.volume is None or snapshot.volume_ema is None:
            warnings.append("Volume confirmation is unavailable from the current data source")
        else:
            if snapshot.volume > snapshot.volume_ema:
                volume_confirmed = True
                score += 15
                reasons.append("Volume is above Volume EMA 20")
            else:
                warnings.append("Volume is not above Volume EMA 20")

        if snapshot.rsi_14 is not None:
            if (bullish and 50 <= snapshot.rsi_14 <= 70) or (not bullish and 30 <= snapshot.rsi_14 <= 50):
                score += 5
                reasons.append("RSI 14 supports the trend without an extreme reading")
            else:
                warnings.append("RSI 14 is not in the preferred trend range")
        if snapshot.atr_14 is not None:
            reasons.append(f"ATR 14 available for volatility-aware stop planning ({snapshot.atr_14:.2f})")

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
        trade_ready = score >= 95 and volume_confirmed and not warnings
        if trade_ready:
            decision = f"STRONG {expected_option} SETUP"
        else:
            decision = "NO TRADE"
        return {
            "score": score, "direction": direction, "decision": decision,
            "reasons": reasons, "warnings": warnings,
            "volume_confirmed": volume_confirmed, "trade_ready": trade_ready,
        }
