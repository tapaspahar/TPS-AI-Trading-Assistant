class NextDayBiasEngine:
    """Evidence score for the next session; never a price guarantee."""

    def analyze(self, values):
        required = ("spot_close", "spot_ema5", "spot_ema20", "spot_ema50", "spot_vwap", "spot_supertrend",
                    "future_close", "future_ema5", "future_ema20", "future_ema50", "future_vwap", "future_supertrend",
                    "put_support", "call_resistance")
        data = {key: float(values[key]) for key in required}
        if any(value <= 0 for value in data.values()):
            raise ValueError("Verify every required closing value before analysis.")
        if data["put_support"] >= data["call_resistance"]:
            raise ValueError("Put support must be below call resistance.")

        votes, evidence = [], []
        self._trend_votes("Spot", data, "spot", votes, evidence)
        self._trend_votes("Future", data, "future", votes, evidence)
        basis = data["future_close"] - data["spot_close"]
        votes.append(0.5 if basis > 0 else -0.5 if basis < 0 else 0)
        evidence.append(f"Future basis: {basis:+,.2f} points")

        pcr = float(values.get("oi_pcr", 1) or 1)
        if pcr >= 1.10:
            votes.append(1); evidence.append(f"OI PCR {pcr:.2f} supports bullish positioning")
        elif pcr <= 0.90:
            votes.append(-1); evidence.append(f"OI PCR {pcr:.2f} supports bearish positioning")
        else:
            votes.append(0); evidence.append(f"OI PCR {pcr:.2f} is neutral")

        score = sum(votes)
        max_score = sum(abs(vote) for vote in votes) or 1
        confidence = min(95, int(50 + abs(score) / max_score * 45))
        if score >= 2.5:
            bias = "BULLISH"
        elif score <= -2.5:
            bias = "BEARISH"
        else:
            bias = "RANGE-BOUND / MIXED"

        atr = max(0.0, float(values.get("atr", 0) or 0))
        straddle = max(0.0, float(values.get("atm_call", 0) or 0) + float(values.get("atm_put", 0) or 0))
        expected_move = max(atr, straddle, (data["call_resistance"] - data["put_support"]) / 2)
        lower = max(data["put_support"], data["spot_close"] - expected_move)
        upper = min(data["call_resistance"], data["spot_close"] + expected_move)
        return {
            "bias": bias, "confidence": confidence, "score": score,
            "support": data["put_support"], "resistance": data["call_resistance"],
            "lower": lower, "upper": upper, "basis": basis, "evidence": evidence,
            "bullish_above": data["call_resistance"], "bearish_below": data["put_support"],
        }

    @staticmethod
    def _trend_votes(label, data, prefix, votes, evidence):
        close, ema5 = data[f"{prefix}_close"], data[f"{prefix}_ema5"]
        ema20, ema50 = data[f"{prefix}_ema20"], data[f"{prefix}_ema50"]
        vwap, supertrend = data[f"{prefix}_vwap"], data[f"{prefix}_supertrend"]
        price_vote = 1 if close > vwap else -1
        ema_vote = 1 if ema5 > ema20 > ema50 else -1 if ema5 < ema20 < ema50 else 0
        st_vote = 1 if close > supertrend else -1
        votes.extend((price_vote, ema_vote, st_vote))
        evidence.extend((
            f"{label} close {'above' if price_vote > 0 else 'below'} VWAP",
            f"{label} EMA stack {'bullish' if ema_vote > 0 else 'bearish' if ema_vote < 0 else 'mixed'}",
            f"{label} is on the {'bullish' if st_vote > 0 else 'bearish'} side of SuperTrend",
        ))
