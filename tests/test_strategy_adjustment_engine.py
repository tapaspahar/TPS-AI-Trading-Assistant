import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from core.settings_store import SettingsStore
from engine.strategy_adjustment_engine import monitor_strategy_plan


def _leg(action, option_type, strike):
    return {"action": action, "option_type": option_type, "strike": strike,
            "symbol": f"NIFTY-{strike}-{option_type}", "lot_size": 65}


class StrategyAdjustmentEngineTests(unittest.TestCase):
    def test_healthy_plan_stays_unchanged(self):
        plan = {
            "strategy": "Bull Call Debit Spread",
            "spot": 24500,
            "expected_daily_range": 100,
            "legs": [_leg("BUY", "CE", 24500), _leg("SELL", "CE", 24600)],
        }
        result = monitor_strategy_plan(plan, {"spot": 24510, "bias": "BULLISH", "state": "WAIT", "chain": {"quote_rows": []}})
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["decision"], "DO NOTHING")
        self.assertEqual(result["strategy_health"], 90)

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

    def test_confirmed_bear_put_to_bull_call_switch_closes_old_plan_first(self):
        plan = {
            "strategy": "Bear Put Debit Spread", "spot": 24500, "net_type": "DEBIT", "net_premium": 30,
            "expected_daily_range": 100, "breakevens": [24470], "expiry": "20 Aug 2026",
            "management_reference": {"target_profit": 1000, "loss_review_amount": 500},
            "legs": [_leg("BUY", "PE", 24500), _leg("SELL", "PE", 24400)],
        }
        latest = {
            "spot": 24530, "bias": "BULLISH", "state": "REVIEW CANDIDATE",
            "strategy": "Bull Call Debit Spread", "expiry": "27 Aug 2026",
            "legs": [_leg("BUY", "CE", 24500), _leg("SELL", "CE", 24600)],
            "chain": {"quote_rows": []},
        }
        result = monitor_strategy_plan(plan, latest)
        self.assertEqual(result["state"], "EXIT / REASSESS")
        self.assertEqual(result["decision"], "EXIT & SWITCH SIDE")
        self.assertEqual(result["strategy_health"], 20)
        self.assertEqual(result["transition"], "PE -> CE")
        self.assertEqual(result["replacement_strategy"], "Bull Call Debit Spread")
        self.assertTrue(all(action["step"].startswith("1.") for action in result["actions"][:2]))
        self.assertTrue(all(action["step"].startswith("2.") for action in result["actions"][2:]))

    def test_target_reference_requests_controlled_exit(self):
        legs = [_leg("BUY", "CE", 24500), _leg("SELL", "CE", 24600)]
        plan = {
            "strategy": "Bull Call Debit Spread", "spot": 24500, "net_type": "DEBIT", "net_premium": 20,
            "expected_daily_range": 100, "breakevens": [24520],
            "management_reference": {"target_profit": 300, "loss_review_amount": 400}, "legs": legs,
        }
        quotes = [
            {"symbol": legs[0]["symbol"], "bid": 30, "ask": 30, "ltp": 30},
            {"symbol": legs[1]["symbol"], "bid": 5, "ask": 5, "ltp": 5},
        ]
        result = monitor_strategy_plan(plan, {"spot": 24510, "bias": "BULLISH", "state": "WAIT", "chain": {"quote_rows": quotes}})
        self.assertEqual(result["estimated_pnl"], 325.0)
        self.assertEqual(result["state"], "EXIT / REASSESS")
        self.assertEqual(result["decision"], "BOOK PAPER TARGET")
        self.assertIn("target reference reached", result["reason"])


if __name__ == "__main__":
    unittest.main()
