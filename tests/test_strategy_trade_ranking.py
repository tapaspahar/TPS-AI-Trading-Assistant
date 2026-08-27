import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.database_manager import Database
from core.market_session import IST
from ui.pages.strategy_trades_page import candidate_structure_key, capturable_strategy_candidates, strategy_capture_window


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

    def test_all_eligible_candidates_reach_paper_validation_pipeline(self):
        aligned = {"strategy": "Bull Call Debit Spread", "eligible": True, "market_alignment": True}
        wrong_side = {"strategy": "Bear Put Debit Spread", "eligible": True, "market_alignment": False}
        comparison_only = {"strategy": "Long Straddle", "eligible": False, "market_alignment": True}

        captured = capturable_strategy_candidates(
            [wrong_side, comparison_only, aligned], remaining=30
        )

        self.assertEqual(captured, [wrong_side, aligned])
        self.assertNotIn(comparison_only, captured)

    def test_capture_pipeline_respects_daily_remaining_limit(self):
        catalog = [
            {"strategy": f"Strategy {index}", "eligible": True, "market_alignment": True}
            for index in range(3)
        ]

        self.assertEqual(len(capturable_strategy_candidates(catalog, remaining=2)), 2)
        self.assertEqual(capturable_strategy_candidates(catalog, remaining=0), [])

    def test_strategy_capture_waits_for_first_fifteen_minutes(self):
        settings = {"market_pre_open_time": "09:00", "market_open_time": "09:15", "market_close_time": "15:30"}
        stage, ready = strategy_capture_window(datetime(2026, 8, 26, 9, 29, tzinfo=IST), settings)
        self.assertEqual(stage, "OBSERVING")
        self.assertEqual(ready.strftime("%H:%M"), "09:30")
        self.assertEqual(strategy_capture_window(datetime(2026, 8, 26, 9, 30, tzinfo=IST), settings)[0], "CHECKING")

    def test_structure_key_keeps_same_combination_unique_across_candles(self):
        candidate = {"legs": [{"action": "BUY", "option_type": "CE", "strike": 24500, "lots": 1}]}
        self.assertEqual(candidate_structure_key(candidate), "BUY:CE:24500:1")

    def test_market_close_review_is_saved_from_closed_results(self):
        self._capture_closed("Bull Call", "Cutie Bull", "2026-08-26T09:30:00", 125, "TRENDING")
        self._capture_closed("Iron Condor", "Cutie Range", "2026-08-26T09:35:00", -25, "TRENDING")
        review = self.db.save_strategy_session_review(datetime.now().strftime("%d-%m-%Y"), "NIFTY", "BULLISH", "TRENDING")
        self.assertIsNotNone(review)
        self.assertEqual(review["total_strategies"], 2)
        self.assertEqual(review["wins"], 1)
        self.assertEqual(review["best_strategy"], "Cutie Bull")

    def test_market_close_reconciliation_closes_open_rows_and_backfills_review(self):
        candidate = {
            "strategy": "Bull Call Debit Spread", "friendly_name": "Cutie Rocket Shield",
            "family": "DIRECTIONAL", "bias": "BULLISH",
            "legs": [{"action": "BUY", "option_type": "CE", "strike": 100, "lots": 1, "quantity": 65, "price": 10}],
            "max_profit": 100, "max_loss": 50, "capital_required": 50,
            "entry_cashflow": -50, "return_on_capital": 20, "breakevens": [105],
            "profit_zone": "ABOVE 105", "scenario_profitable_percent": 60,
            "rank_score": 75, "explanation": "test",
        }
        today = datetime.now().strftime("%d-%m-%Y")
        self.db.save_strategy_trade(candidate, {
            "symbol": "NIFTY", "spot": 100, "expiry": "TEST",
            "candle_time": "2026-08-26T09:30:00", "market_regime": "TRENDING",
        })

        result = self.db.finalize_open_strategy_sessions(today)

        self.assertEqual(len(result), 1)
        trade = self.db.get_strategy_trades(today)[0]
        self.assertEqual(trade["status"], "CLOSED")
        self.assertIn(trade["outcome"], {"MARKET CLOSE EXIT", "LOSS REVIEW EXIT", "TARGET BENEFIT REACHED"})
        self.assertTrue(trade["exit_at"])
        reviews = self.db.get_strategy_session_reviews()
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["total_strategies"], 1)

    def test_daily_strategy_pnl_combines_closed_and_open_marks(self):
        today = datetime.now().strftime("%d-%m-%Y")
        self._capture_closed("Closed Winner", "Cutie Winner", "2026-08-26T09:30:00", 125)
        candidate = {
            "strategy": "Open Spread", "friendly_name": "Cutie Open", "family": "DIRECTIONAL", "bias": "BULLISH",
            "legs": [{"action": "BUY", "option_type": "CE", "strike": 200, "lots": 1}],
            "max_profit": 100, "max_loss": 50, "capital_required": 50, "entry_cashflow": -50,
            "return_on_capital": 20, "breakevens": [205], "profit_zone": "ABOVE 205",
            "scenario_profitable_percent": 60, "rank_score": 75, "explanation": "test",
        }
        trade_id = self.db.save_strategy_trade(candidate, {
            "symbol": "NIFTY", "spot": 200, "expiry": "TEST", "candle_time": "2026-08-26T09:35:00",
        })
        self.db.cursor.execute("UPDATE strategy_trades SET current_pnl=? WHERE id=?", (-25, trade_id))
        self.db.connection.commit()
        daily = self.db.get_strategy_daily_pnl(today)
        self.assertEqual(daily["open_count"], 1)
        self.assertEqual(daily["closed_count"], 1)
        self.assertEqual(float(daily["combined_pnl"]), 100.0)

    def test_daily_limit_closes_every_open_strategy_at_latest_mark(self):
        today = datetime.now().strftime("%d-%m-%Y")
        for index in range(2):
            candidate = {
                "strategy": f"Spread {index}", "friendly_name": f"Cutie {index}", "family": "DIRECTIONAL", "bias": "BULLISH",
                "legs": [{"action": "BUY", "option_type": "CE", "strike": 300 + index, "lots": 1}],
                "max_profit": 100, "max_loss": 50, "capital_required": 50, "entry_cashflow": -50,
                "return_on_capital": 20, "breakevens": [305], "profit_zone": "ABOVE",
                "scenario_profitable_percent": 60, "rank_score": 75, "explanation": "test",
            }
            trade_id = self.db.save_strategy_trade(candidate, {
                "symbol": "NIFTY", "spot": 300, "expiry": "TEST", "candle_time": f"2026-08-26T09:{40 + index * 5}:00",
            })
            self.db.cursor.execute("UPDATE strategy_trades SET current_pnl=? WHERE id=?", (75 + index, trade_id))
        self.db.connection.commit()
        events = self.db.close_strategy_trades_for_daily_limit(today, "DAILY TARGET HIT")
        self.assertEqual(len(events), 2)
        rows = self.db.get_strategy_trades(today)
        self.assertTrue(all(row["status"] == "CLOSED" for row in rows))
        self.assertTrue(all(row["outcome"] == "DAILY TARGET HIT" for row in rows))
        self.assertEqual(sum(float(row["realized_pnl"]) for row in rows), 151.0)

    def test_per_strategy_target_closes_only_the_strategy_that_hits(self):
        today = datetime.now().strftime("%d-%m-%Y")
        for index, strike in enumerate((400, 500)):
            candidate = {
                "strategy": f"Per Trade {index}", "friendly_name": f"Cutie Per Trade {index}",
                "family": "DIRECTIONAL", "bias": "BULLISH",
                "legs": [{"action": "BUY", "option_type": "CE", "strike": strike, "symbol": f"OPT{strike}",
                          "lots": 1, "quantity": 1, "price": 10}],
                "max_profit": 100, "max_loss": 50, "capital_required": 50, "entry_cashflow": -10,
                "return_on_capital": 20, "breakevens": [strike + 10], "profit_zone": "ABOVE",
                "scenario_profitable_percent": 60, "rank_score": 75, "explanation": "test",
            }
            self.db.save_strategy_trade(candidate, {
                "symbol": "NIFTY", "spot": 450, "expiry": "TEST",
                "candle_time": f"2026-08-26T10:{index * 5:02d}:00",
                "strategy_target_profit_amount": 20, "strategy_stop_loss_amount": 15,
            })
        self.db.update_strategy_trades("NIFTY", 455, candle_time=f"{today} 10:10", quote_rows=[
            {"symbol": "OPT400", "option_type": "CE", "strike": 400, "bid": 31},
            {"symbol": "OPT500", "option_type": "CE", "strike": 500, "bid": 10},
        ])
        rows = self.db.get_strategy_trades(today)
        states = {row["strategy_name"]: row["status"] for row in rows}
        self.assertEqual(states["Per Trade 0"], "CLOSED")
        self.assertEqual(states["Per Trade 1"], "OPEN")


if __name__ == "__main__":
    unittest.main()
