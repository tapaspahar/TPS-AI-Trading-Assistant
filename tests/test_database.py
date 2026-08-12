import tempfile
import unittest
import csv
import copy
from pathlib import Path

from core.database_manager import Database
from models.trade import Trade


def sample_trade(**changes):
    values = dict(
        trade_date="01-08-2026", trade_time="09:30", market="OPTIONS", symbol="NIFTY",
        expiry="", strike="25000", option="CE", entry=120.0, exit=145.0,
        stoploss=100.0, target=180.0, quantity=75, trend=True, vwap=True,
        ema=True, volume=True, oi=True, psychology_before="Calm",
    )
    values.update(changes)
    return Trade(**values)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "trades.db")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_save_trade_calculates_metrics_and_ai_analysis(self):
        trade = sample_trade()
        trade_id = self.db.save_trade(trade)
        saved = self.db.get_all_trades()

        self.assertEqual(trade_id, 1)
        self.assertEqual((trade.pnl, trade.rr_ratio), (1875.0, 3.0))
        self.assertEqual((trade.ai_score, trade.ai_decision), (90, "STRONG BUY"))
        self.assertEqual(saved[0][2], "NIFTY")
        self.assertEqual(saved[0][7], 1875.0)

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Quantity"):
            self.db.save_trade(sample_trade(quantity=0))

    def test_open_trade_can_be_closed_later(self):
        trade_id = self.db.save_open_trade(sample_trade(exit=0.0))
        open_trade = self.db.get_trade(trade_id)
        self.assertEqual(open_trade["status"], "OPEN")
        self.assertEqual(open_trade["pnl"], 0.0)

        self.assertTrue(self.db.close_trade(trade_id, 145.0, "Target Hit"))
        closed_trade = self.db.get_trade(trade_id)
        self.assertEqual(closed_trade["status"], "CLOSED")
        self.assertEqual((closed_trade["exit"], closed_trade["pnl"], closed_trade["rr_ratio"]), (145.0, 1875.0, 3.0))
        self.assertEqual(closed_trade["outcome"], "TARGET HIT")

    def test_market_snapshots_are_saved_once_per_timeframe_bucket(self):
        snapshot = {
            "captured_at": "2026-08-03T10:15", "trade_date": "03-08-2026", "symbol": "NIFTY", "timeframe": "5m",
            "open": 24500, "high": 24520, "low": 24490, "close": 24510,
            "volume": 1000, "volume_ema": 900, "ema_5": 24505, "ema_20": 24495, "ema_50": 24480,
            "vwap": 24500, "supertrend": 24470, "rsi_14": 60, "atr_14": 20,
            "oi_pcr": 1.1, "volume_pcr": 0.9, "put_support": 24500, "call_resistance": 24600, "option_contracts": 22,
        }
        self.assertTrue(self.db.save_market_snapshot(snapshot))
        self.assertFalse(self.db.save_market_snapshot(snapshot))
        saved = self.db.get_market_snapshots("03-08-2026")
        self.assertEqual((len(saved), saved[0]["symbol"], saved[0]["oi_pcr"]), (1, "NIFTY", 1.1))

    def test_pcr_observations_keep_latest_sentiment_context(self):
        first = {
            "captured_at": "2026-08-12T10:00:00+05:30", "symbol": "NIFTY", "expiry": "2026-08-27",
            "call_oi": 100, "put_oi": 120, "call_oi_change": 5, "put_oi_change": 20,
            "pcr_oi": 1.2, "call_volume": 50, "put_volume": 70, "pcr_volume": 1.4,
            "sentiment": "BULLISH OI BIAS", "confidence": 70,
        }
        self.db.save_pcr_observation(first)
        saved = self.db.get_latest_pcr_observation("NIFTY", "2026-08-27")
        self.assertEqual((saved["sentiment"], saved["pcr_oi"]), ("BULLISH OI BIAS", 1.2))
        self.assertEqual(len(self.db.get_pcr_observations("NIFTY")), 1)

    def test_gap_probability_forecast_is_saved_and_resolved_from_next_open(self):
        forecast = {
            "forecast_date": "2026-08-12", "target_date": "2026-08-13",
            "generated_at": "2026-08-12T15:21:00+05:30", "symbol": "NIFTY", "stage": "3:20 FINAL",
            "predicted_class": "GAP UP", "gap_up_probability": 48.0, "flat_probability": 30.0,
            "gap_down_probability": 22.0, "confidence": 61, "data_quality": 90,
            "prior_close": 25000, "inputs": {"fii_net": 1000}, "evidence": ["test"],
        }
        self.db.save_gap_probability_forecast(forecast)
        self.db.save_market_snapshot({
            "captured_at": "2026-08-13T09:15:00+05:30", "trade_date": "13-08-2026", "symbol": "NIFTY", "timeframe": "5m",
            "open": 25050, "high": 25060, "low": 25040, "close": 25055, "volume": 100, "volume_ema": 90,
            "ema_5": 25050, "ema_20": 25020, "ema_50": 25000, "vwap": 25048, "supertrend": 25010,
            "rsi_14": 60, "atr_14": 20, "oi_pcr": 1.0, "volume_pcr": 1.0,
            "put_support": 25000, "call_resistance": 25100, "option_contracts": 10,
        })
        self.assertEqual(self.db.resolve_gap_probability_outcomes(), 1)
        saved = self.db.get_gap_probability_forecasts("NIFTY")[0]
        self.assertEqual((saved["actual_class"], saved["correct"]), ("GAP UP", 1))

    def test_auto_trade_attempt_history_deduplicates_candles_and_exports(self):
        result = {
            "status": "No paper trade: TPS v2 confirmations 4/6.",
            "attempt": {
                "checked_at": "2026-08-04T11:16:00", "candle_time": "2026-08-04T11:10:00+05:30",
                "future_symbol": "NIFTY-FUT", "candidate": "CE", "capture": {}, "chain": {}, "blockers": ["Low volume"],
                "chart": {"decision": "NO TRADE", "score": 67, "strategy": {"passed": 4, "total": 6}},
            },
        }
        self.assertTrue(self.db.save_auto_trade_attempt("NIFTY", result))
        self.assertFalse(self.db.save_auto_trade_attempt("NIFTY", result))
        resolved = copy.deepcopy(result)
        resolved["status"] = "No paper trade after successful retry"
        resolved["attempt"]["chart"] = {"decision": "NO TRADE", "score": 83, "strategy": {"passed": 5, "total": 6}}
        resolved.pop("retry_pending", None)
        self.assertTrue(self.db.save_auto_trade_attempt("NIFTY", resolved))
        rows = self.db.get_auto_trade_attempts("04-08-2026")
        self.assertEqual((len(rows), rows[0]["confirmations_passed"], rows[0]["outcome"]), (1, 5, "NO TRADE"))
        path = Path(self.temp_dir.name) / "attempts.csv"
        self.assertEqual(self.db.export_auto_trade_attempts(path, "04-08-2026"), 1)
        self.assertIn("candle_time", path.read_text(encoding="utf-8-sig"))

    def test_open_ce_trade_gets_one_reversal_alert(self):
        trade_id = self.db.save_open_trade(sample_trade(exit=0.0))
        for timeframe in ("5m", "15m"):
            self.db.save_market_snapshot({
                "captured_at": f"2026-08-03T10:{'15' if timeframe == '5m' else '30'}", "trade_date": "03-08-2026",
                "symbol": "NIFTY", "timeframe": timeframe, "open": 100, "high": 101, "low": 90, "close": 92,
                "volume": 1000, "volume_ema": 900, "ema_5": 95, "ema_20": 96, "ema_50": 97,
                "vwap": 98, "supertrend": 94, "rsi_14": 40, "atr_14": 4,
                "oi_pcr": 0.8, "volume_pcr": 0.7, "put_support": 90, "call_resistance": 100, "option_contracts": 22,
            })
        first = self.db.evaluate_open_trade_alerts("NIFTY")
        self.assertEqual((len(first), first[0]["trade_id"]), (1, trade_id))
        self.assertEqual(self.db.evaluate_open_trade_alerts("NIFTY"), [])

    def test_summary_aggregates_saved_trades(self):
        self.db.save_trade(sample_trade())
        self.db.save_trade(sample_trade(symbol="BANKNIFTY", entry=100, exit=90, stoploss=80, target=140, quantity=10))

        summary = self.db.get_summary()
        self.assertEqual(summary["trades"], 2)
        self.assertEqual(summary["winning_trades"], 1)
        self.assertEqual(summary["pnl"], 1775.0)
        self.assertEqual(summary["win_rate"], 50.0)

    def test_validation_report_uses_only_fully_confirmed_closed_trades(self):
        trade_id = self.db.save_open_trade(sample_trade(exit=0.0))
        self.db.close_trade(trade_id, 145.0, "Target Hit")
        self.db.save_trade(sample_trade(trend=False, symbol="BANKNIFTY"))

        report = self.db.get_validation_report()
        self.assertEqual((report["samples"], report["target_hits"], report["stoploss_hits"]), (1, 1, 0))
        self.assertEqual(report["accuracy"], 100.0)
        self.assertIn("30", report["status"])

    def test_rule_version_report_groups_closed_trades(self):
        self.db.save_trade(sample_trade(setup="TPS V2 strict"))
        rows = self.db.get_rule_version_report()
        self.assertEqual((rows[0]["rule_version"], rows[0]["samples"]), ("TPS V2 strict", 1))

    def test_day_summary_filters_by_journal_date(self):
        self.db.save_trade(sample_trade())
        self.db.save_trade(sample_trade(trade_date="02-08-2026", symbol="FINNIFTY"))

        self.assertEqual(self.db.get_day_summary("01-08-2026"), {"trades": 1, "pnl": 1875.0})

    def test_delete_and_csv_export(self):
        trade_id = self.db.save_trade(sample_trade())
        export_path = Path(self.temp_dir.name) / "journal.csv"
        self.assertEqual(self.db.export_csv(export_path), 1)
        with export_path.open(encoding="utf-8-sig", newline="") as file:
            exported = list(csv.DictReader(file))
        self.assertEqual(exported[0]["symbol"], "NIFTY")
        self.assertTrue(self.db.delete_trade(trade_id))
        self.assertFalse(self.db.delete_trade(trade_id))
        self.assertEqual(self.db.get_summary()["trades"], 0)


if __name__ == "__main__":
    unittest.main()
