import unittest
from unittest.mock import patch

from services.auto_paper_trader import run_auto_paper_cycle


class AutoPaperTraderTests(unittest.TestCase):
    @patch("services.auto_paper_trader.Database")
    def test_does_not_create_new_trade_while_open_paper_trade_exists(self, database_type):
        database = database_type.return_value
        database.paper_trade_progress.return_value = {"trades": 1, "days": 1, "open_trades": 1, "target_hits": 0, "stoploss_hits": 0}
        result = run_auto_paper_cycle(object(), "NIFTY", {"max_trades_per_day": 5})
        self.assertIn("open paper trade", result["status"])
        database.close.assert_called_once()
