import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database


class StrategyTradeRankingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "strategy-ranking.db")

    def tearDown(self):
        self.db.connection.close()
        self.folder.cleanup()

    def _capture_closed(self, strategy, friendly, candle, pnl, regime="TRENDING"):
        candidate = {
            "strategy": strategy,
            "friendly_name": friendly,
            "family": "DIRECTIONAL",
            "bias": "BULLISH",
            "legs": [{"action": "BUY", "option_type": "CE", "strike": 100, "lots": 1}],
            "max_profit": 100,
            "max_loss": 50,
            "capital_required": 50,
            "entry_cashflow": -50,
            "return_on_capital": 20,
            "breakevens": [105],
            "profit_zone": "ABOVE 105",
            "scenario_profitable_percent": 60,
            "rank_score": 75,
            "explanation": "test",
        }
        trade_id = self.db.save_strategy_trade(candidate, {
            "symbol": "NIFTY", "spot": 100, "expiry": "TEST", "candle_time": candle,
            "market_regime": regime,
        })
        self.db.cursor.execute(
            "UPDATE strategy_trades SET status='CLOSED', outcome='TEST', realized_pnl=? WHERE id=?",
            (pnl, trade_id),
        )
        self.db.connection.commit()

    def test_actual_win_rate_is_ranked_before_total_pnl(self):
        self._capture_closed("High Win", "Cutie High Win", "2026-01-01T09:20:00", 10)
        self._capture_closed("High Win", "Cutie High Win", "2026-01-01T09:25:00", 5, "RANGE")
        self._capture_closed("Lower Win", "Cutie Lower Win", "2026-01-01T09:30:00", 1000)
        self._capture_closed("Lower Win", "Cutie Lower Win", "2026-01-01T09:35:00", -1)

        ranking = self.db.get_strategy_performance()

        self.assertEqual(ranking[0]["strategy_name"], "High Win")
        self.assertEqual(float(ranking[0]["win_rate"]), 100.0)
        self.assertEqual(int(ranking[0]["samples"]), 2)
        self.assertIn("TRENDING", ranking[0]["market_regimes"])
        self.assertIn("RANGE", ranking[0]["market_regimes"])


if __name__ == "__main__":
    unittest.main()
