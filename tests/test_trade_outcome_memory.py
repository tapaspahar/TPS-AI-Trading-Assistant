import json
import tempfile
import unittest
from pathlib import Path

from core.database_manager import Database
from engine.trade_outcome_memory import build_trade_fingerprint, similarity_score


class TradeOutcomeMemoryTests(unittest.TestCase):
    def test_similarity_is_condition_context_not_probability(self):
        trade = {"symbol": "NIFTY", "option_type": "CE", "ai_score": 82}
        plan = {"market_environment": {"regime": "TRENDING", "vix_zone": "NORMAL"},
                "strategy": {"direction": "BULLISH", "score": 82}}
        fingerprint = build_trade_fingerprint(trade, plan)
        self.assertEqual(similarity_score(fingerprint, fingerprint), 100)

    def test_close_creates_automatic_review_and_searchable_analog(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            plan = {
                "underlying": "NIFTY", "option_type": "CE", "entry": 100, "stoploss": 90,
                "target": 120, "quantity": 65, "confidence": 80,
                "contract": {"exchange": "NFO", "token": "1", "symbol": "NIFTYCE", "strike": 24000, "expiry": "2026-08-27"},
                "market_environment": {"regime": "TRENDING", "vix_zone": "NORMAL"},
                "strategy": {"direction": "BULLISH", "score": 80},
                "evidence_context": {"volume_ratio": 1.6},
            }
            trade_id = db.save_paper_trade(plan)
            db.cursor.execute("UPDATE paper_trade_links SET mfe=20, mae=3 WHERE trade_id=?", (trade_id,))
            db.connection.commit()
            self.assertTrue(db.close_trade(trade_id, 120, "TARGET HIT"))
            review = db.get_trade_outcome_review(trade_id)
            self.assertIsNotNone(review)
            self.assertIn("Target achieve", review["review_text"])
            matches = db.find_trade_outcome_analogs(json.loads(review["fingerprint_json"]))
            self.assertEqual(matches[0]["trade_id"], trade_id)
            self.assertEqual(matches[0]["outcome"], "TARGET HIT")
            db.close()


if __name__ == "__main__":
    unittest.main()
