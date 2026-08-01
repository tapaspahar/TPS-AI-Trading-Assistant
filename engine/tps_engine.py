from engine.psychology_engine import PsychologyEngine


class TPSEngine:

    def __init__(self):

        self.psychology = PsychologyEngine()

    def calculate(self, trade):

        score = 0

        reasons = []

        if trade.trend:
            score += 20
            reasons.append("Trend Confirmed")

        if trade.vwap:
            score += 15
            reasons.append("VWAP Confirmed")

        if trade.ema:
            score += 10
            reasons.append("EMA Alignment")

        if trade.volume:
            score += 15
            reasons.append("Volume Confirmed")

        if trade.oi:
            score += 20
            reasons.append("Option Chain Confirmed")

        psychology_score = self.psychology.evaluate(
    trade.psychology_before)

        score += psychology_score

        if score >= 90:

            decision = "STRONG BUY"

        elif score >= 75:

            decision = "BUY"

        elif score >= 60:

            decision = "WATCH"

        else:

            decision = "NO TRADE"

        return {

            "score": score,

            "decision": decision,

            "reasons": reasons

        }