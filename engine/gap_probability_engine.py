"""Transparent three-way next-session opening-gap probability model."""

from __future__ import annotations

import math


class GapProbabilityEngine:
    """Estimate Gap Up / Flat / Gap Down without pretending certainty.

    The overnight uncertainty blend is intentional: domestic closing data cannot
    know later global news, GIFT NIFTY movement, currency moves or policy events.
    """

    GAP_THRESHOLD_PERCENT = 0.15

    def analyze(self, values: dict) -> dict:
        spot = float(values.get("spot_close") or 0)
        future = float(values.get("future_close") or 0)
        if spot <= 0 or future <= 0:
            raise ValueError("Positive Spot and Future closing values are required.")

        votes, evidence = [], []
        for prefix, label in (("spot", "Spot"), ("future", "Future")):
            close = float(values.get(f"{prefix}_close") or 0)
            ema5 = float(values.get(f"{prefix}_ema5") or 0)
            ema20 = float(values.get(f"{prefix}_ema20") or 0)
            ema50 = float(values.get(f"{prefix}_ema50") or 0)
            vwap = float(values.get(f"{prefix}_vwap") or 0)
            supertrend = float(values.get(f"{prefix}_supertrend") or 0)
            if all((ema5, ema20, ema50)):
                ema_vote = 1 if ema5 > ema20 > ema50 else -1 if ema5 < ema20 < ema50 else 0
                votes.append((ema_vote, 1.0))
                evidence.append(f"{label} EMA stack: {'bullish' if ema_vote > 0 else 'bearish' if ema_vote < 0 else 'mixed'}")
            if vwap:
                vote = 1 if close > vwap else -1
                votes.append((vote, 0.75)); evidence.append(f"{label} close {'above' if vote > 0 else 'below'} VWAP")
            if supertrend:
                vote = 1 if close > supertrend else -1
                votes.append((vote, 0.65)); evidence.append(f"{label} on {'bullish' if vote > 0 else 'bearish'} side of SuperTrend")

        basis_percent = (future - spot) / spot * 100
        basis_vote = max(-1.0, min(1.0, basis_percent / 0.25))
        votes.append((basis_vote, 0.9))
        evidence.append(f"Future basis {basis_percent:+.3f}%")

        pcr = float(values.get("oi_pcr") or 0)
        if pcr:
            pcr_vote = max(-1.0, min(1.0, (pcr - 1.0) / 0.25))
            votes.append((pcr_vote, 0.7)); evidence.append(f"OI-PCR {pcr:.2f} used as secondary context")

        fii = self._optional_float(values.get("fii_net"))
        dii = self._optional_float(values.get("dii_net"))
        flow_weight = 0.0
        if fii is not None or dii is not None:
            fii = fii or 0.0; dii = dii or 0.0
            # Daily institutional cash flow is useful context, but is deliberately
            # capped because it is not a direct overnight-gap signal.
            flow_signal = max(-1.0, min(1.0, (0.70 * fii + 0.30 * dii) / 5000.0))
            votes.append((flow_signal, 0.65)); flow_weight = 0.65
            evidence.append(f"Official/cached institutional cash flow: FII {fii:+,.0f} Cr, DII {dii:+,.0f} Cr")
        else:
            evidence.append("FII/DII flow unavailable; no institutional vote was invented")

        total_weight = sum(weight for _vote, weight in votes) or 1.0
        directional = sum(vote * weight for vote, weight in votes) / total_weight
        # Softmax plus a 38% uniform uncertainty blend prevents false precision.
        logits = {
            "GAP UP": -0.18 + 1.15 * directional,
            "FLAT / INSIDE": 0.32 - 0.42 * abs(directional),
            "GAP DOWN": -0.18 - 1.15 * directional,
        }
        exponentials = {key: math.exp(value) for key, value in logits.items()}
        denominator = sum(exponentials.values())
        raw = {key: value / denominator for key, value in exponentials.items()}
        probabilities = {key: (0.62 * value + 0.38 / 3) * 100 for key, value in raw.items()}
        rounded = {key: round(value, 1) for key, value in probabilities.items()}
        # Keep displayed values exactly at 100.0 after rounding.
        rounded["FLAT / INSIDE"] = round(100.0 - rounded["GAP UP"] - rounded["GAP DOWN"], 1)
        predicted = max(rounded, key=rounded.get)
        completeness = min(100, int(round(total_weight / (6.65 + flow_weight) * 100)))
        margin = sorted(rounded.values(), reverse=True)[0] - sorted(rounded.values(), reverse=True)[1]
        confidence = min(78, int(42 + margin * 1.5 + completeness * 0.16))
        return {
            "predicted_class": predicted,
            "gap_up_probability": rounded["GAP UP"],
            "flat_probability": rounded["FLAT / INSIDE"],
            "gap_down_probability": rounded["GAP DOWN"],
            "confidence": confidence,
            "data_quality": completeness,
            "directional_score": round(directional, 3),
            "basis_percent": round(basis_percent, 3),
            "evidence": evidence,
            "gap_threshold_percent": self.GAP_THRESHOLD_PERCENT,
        }

    @staticmethod
    def _optional_float(value):
        if value is None or str(value).strip() == "":
            return None
        return float(value)
