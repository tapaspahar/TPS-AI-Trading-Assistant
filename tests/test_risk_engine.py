import unittest

from engine.risk_engine import RiskEngine


def assess(**overrides):
    values = dict(capital=100000, risk_percent=1, daily_loss_percent=3,
                  max_trades_per_day=5, trades_today=1, open_trades=0,
                  realized_pnl=0, entry=100, stoploss=90, target=120,
                  lot_size=50, requested_lots=1)
    values.update(overrides)
    return RiskEngine().assess_option_risk(**values)


class RiskEngineTests(unittest.TestCase):
    def test_safe_plan_uses_whole_option_lots(self):
        result = assess()
        self.assertEqual(result["verdict"], "SAFE")
        self.assertEqual(result["risk_per_lot"], 500)
        self.assertEqual(result["safe_lots"], 2)
        self.assertEqual(result["quantity"], 50)

    def test_oversized_plan_recommends_reducing_lots(self):
        self.assertEqual(assess(requested_lots=3)["verdict"], "REDUCE LOTS")

    def test_open_trade_blocks_a_new_plan(self):
        result = assess(open_trades=1)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("already open", result["blockers"][0])

    def test_invalid_long_option_prices_are_rejected(self):
        with self.assertRaises(ValueError):
            assess(stoploss=105)
