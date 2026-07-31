class TPSEngine:

    def calculate_score(self, trade):

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
            reasons.append("Volume Confirmation")

        if trade.oi:
            score += 20
            reasons.append("Option Chain Confirmation")

        if trade.psychology.lower() in ["calm", "confident"]:
            score += 10
            reasons.append("Good Psychology")

        return score, reasons