import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from core.settings_store import SettingsStore
from engine.strategy_adjustment_engine import monitor_strategy_plan


def _leg(action, option_type, strike):
    return {"action": action, "option_type": option_type, "strike": strike,
            "symbol": f"NIFTY-{strike}-{option_type}", "lot_size": 65}


class StrategyAdjustmentEngineTests(unittest.TestCase):
    def test_active_plan_can_survive_restart_in_update_safe_settings(self):
        with TemporaryDirectory() as folder:
            store = SettingsStore(Path(folder) / "settings.json")
            values = store.load()
            values["active_option_strategy_plan"] = {"strategy": "Bull Call Debit Spread", "spot": 24500, "legs": []}
            store.save(values)
            restored = SettingsStore(Path(folder) / "settings.json").load()["active_option_strategy_plan"]
            self.assertEqual(restored["strategy"], "Bull Call Debit Spread")

    def test_iron_condor_breach_closes_only_tested_side_without_naked_leg(self):
        plan = {
            "strategy": "Defined-Risk Iron Condor", "spot": 24500, "net_type": "CREDIT", "net_premium": 20,
            "expected_daily_range": 150, "breakevens": [24280, 24720],
            "legs": [_leg("BUY", "PE", 24200), _leg("SELL", "PE", 24300),
                     _leg("SELL", "CE", 24700), _leg("BUY", "CE", 24800)],
        }
        latest = {"spot": 24730, "bias": "BULLISH", "state": "WAIT", "chain": {"quote_rows": []}}
        result = monitor_strategy_plan(plan, latest)
        self.assertEqual(result["state"], "EXIT / REASSESS")
        self.assertEqual(len(result["actions"]), 2)
        self.assertTrue(all(action["option_type"] == "CE" for action in result["actions"]))
        self.assertEqual({action["action"] for action in result["actions"]}, {"BUY", "SELL"})

    def test_bull_call_invalidates_only_after_bias_and_buffer_move_agree(self):
        plan = {
            "strategy": "Bull Call Debit Spread", "spot": 24500, "net_type": "DEBIT", "net_premium": 30,
            "expected_daily_range": 100, "breakevens": [24530],
            "legs": [_leg("BUY", "CE", 24500), _leg("SELL", "CE", 24600)],
        }
        watch = monitor_strategy_plan(plan, {"spot": 24490, "bias": "BEARISH", "chain": {"quote_rows": []}})
        self.assertEqual(watch["state"], "WATCH")
        exit_result = monitor_strategy_plan(plan, {"spot": 24470, "bias": "BEARISH", "chain": {"quote_rows": []}})
        self.assertEqual(exit_result["state"], "EXIT / REASSESS")
        self.assertEqual(len(exit_result["actions"]), 2)

    def test_hold_estimates_credit_plan_pnl_from_executable_quotes(self):
        legs = [_leg("BUY", "PE", 24200), _leg("SELL", "PE", 24300),
                _leg("SELL", "CE", 24700), _leg("BUY", "CE", 24800)]
        plan = {"strategy": "Defined-Risk Iron Condor", "spot": 24500, "net_type": "CREDIT",
                "net_premium": 20, "expected_daily_range": 100, "breakevens": [24280, 24720], "legs": legs}
        quotes = []
        for leg, ltp in zip(legs, (4, 7, 8, 3)):
            quotes.append({"symbol": leg["symbol"], "bid": ltp, "ask": ltp, "ltp": ltp})
        result = monitor_strategy_plan(plan, {"spot": 24500, "bias": "RANGE / MIXED", "chain": {"quote_rows": quotes}})
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["estimated_pnl"], 780.0)


if __name__ == "__main__":
    unittest.main()
