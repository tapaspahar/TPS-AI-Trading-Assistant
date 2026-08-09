import unittest
from datetime import datetime

from core.market_session import IST
from engine.execution_safety import assess_execution_safety


class ExecutionSafetyTests(unittest.TestCase):
    def base(self):
        now = datetime(2026, 8, 10, 11, 2, tzinfo=IST)
        return dict(
            now=now, candle_time="2026-08-10T11:00:00+05:30",
            quote={"ltp": 100, "volume": 1000, "bid": 99, "ask": 101},
            plan={"entry": 100, "stoploss": 80, "target": 140, "risk_within_cap": True},
            settings={"time_exit_minutes_before_close": 10, "minimum_option_volume": 100,
                      "maximum_option_spread_percent": 8, "minimum_rr_ratio": 1.5,
                      "max_trades_per_day": 5, "news_risk_pause": False},
            progress={"trades": 0, "open_trades": 0, "daily_remaining": 3000},
        )

    def test_valid_execution_context_is_allowed(self):
        self.assertTrue(assess_execution_safety(**self.base())["allowed"])

    def test_spread_cooldown_and_event_are_hard_blockers(self):
        values = self.base(); values["quote"].update({"bid": 90, "ask": 110})
        values["cooldown_remaining"] = 8
        values["event_risk"] = {"blocked": True, "high_impact_events": [{"name": "RBI Policy"}], "available": True}
        result = assess_execution_safety(**values)
        self.assertFalse(result["allowed"])
        self.assertGreaterEqual(len(result["blockers"]), 3)

    def test_event_override_is_audited_but_allows_paper_test(self):
        values = self.base()
        values["settings"]["event_risk_override"] = True
        values["event_risk"] = {"blocked": True, "high_impact_events": [{"name": "RBI Policy"}], "available": True}
        result = assess_execution_safety(**values)
        self.assertTrue(result["allowed"])
        self.assertTrue(any("overridden" in warning for warning in result["warnings"]))
