import unittest
from datetime import datetime
from unittest.mock import patch

from services.auto_paper_trader import _completed_candles, run_auto_paper_cycle, signal_timing_stage


class AutoPaperTraderTests(unittest.TestCase):
    def test_signal_timing_stage_separates_watch_from_final_approval(self):
        settings = {"tps_required_matches": 5, "trade_plan_min_score": 80}
        early = {
            "trade_ready": False, "candidate": "CE", "required": 5, "minimum_score": 80,
            "side_evaluations": {"CE": {"passed": 4, "score": 70}},
        }
        weak = {
            "trade_ready": False, "candidate": "PE", "required": 5, "minimum_score": 80,
            "side_evaluations": {"PE": {"passed": 3, "score": 70}},
        }
        self.assertEqual(signal_timing_stage({"trade_ready": True}, settings), "FIRST VALID")
        self.assertEqual(signal_timing_stage(early, settings), "EARLY WATCH")
        self.assertEqual(signal_timing_stage(weak, settings), "NONE")

    def test_current_forming_candle_is_excluded(self):
        candles = [{"time": "2026-08-04T13:10:00+05:30"}, {"time": "2026-08-04T13:15:00+05:30"}]
        completed = _completed_candles(candles, datetime(2026, 8, 4, 13, 15, 8))
        self.assertEqual([item["time"] for item in completed], ["2026-08-04T13:10:00+05:30"])

    @patch("services.auto_paper_trader.evaluate_tps_entry_v2")
    @patch("services.auto_paper_trader.analyze_option_chain")
    @patch("services.auto_paper_trader.DecisionEngine")
    @patch("services.auto_paper_trader.build_live_capture")
    @patch("services.auto_paper_trader.OptionContractService")
    @patch("services.auto_paper_trader.Database")
    def test_does_not_create_new_trade_while_open_paper_trade_exists(self, database_type, service_type, build_capture, decision_type, analyze_chain, evaluate_strategy):
        database = database_type.return_value
        database.paper_trade_progress.return_value = {"trades": 1, "days": 1, "open_trades": 1, "target_hits": 0, "stoploss_hits": 0}
        service_type.return_value.get_front_month_future.return_value = {"exchange": "NFO", "token": "future", "symbol": "NIFTY-FUT"}
        service_type.return_value.get_contracts.return_value = [{"exchange": "NFO", "token": "ce", "symbol": "NIFTYCE", "strike": 25000, "option_type": "CE", "expiry": "2026-08-27", "lot_size": 75}]
        build_capture.return_value = {"close": "25010", "ema_5": "25005", "ema_20": "25000", "ema_50": "24950", "vwap": "25000", "supertrend": "24990", "volume": "1000", "volume_ema": "500", "rsi_14": "55", "atr_14": "20", "volume_ratio": "2", "candle_direction": "BULLISH", "fake_breakout_risk": False, "candle_time": "2026-08-04T11:10:00+05:30"}
        decision_type.return_value.evaluate.return_value = {"score": 100}
        analyze_chain.return_value = {"pcr_oi": 1.0, "pcr_volume": 1.0, "quote_rows": [], "call_resistance": 25100, "put_support": 24900}
        evaluate_strategy.return_value = {"score": 100, "direction": "BULLISH", "candidate": "CE", "decision": "TPS V2 CE ENTRY CONFIRMED", "trade_ready": True, "passed": 6, "total": 6, "confirmations": [{"name": "Directional volume", "passed": True, "detail": "confirmed"}], "blockers": []}
        client = unittest.mock.Mock()
        client.get_recent_candles.return_value = [{"time": "2026-08-04T11:10:00+05:30"}] * 51
        client.get_option_quote.return_value = {"ltp": 25010}
        client.get_option_chain_quotes.return_value = []
        result = run_auto_paper_cycle(client, "NIFTY", {"max_trades_per_day": 5})
        self.assertIn("operational safety limit", result["status"])
        self.assertTrue(any("open paper trade" in reason for reason in result["attempt"]["blockers"]))
        database.save_auto_trade_attempt.assert_called_once()
        database.close.assert_called_once()

    @patch("services.auto_paper_trader.evaluate_tps_entry_v2")
    @patch("services.auto_paper_trader.analyze_option_chain")
    @patch("services.auto_paper_trader.DecisionEngine")
    @patch("services.auto_paper_trader.build_live_capture")
    @patch("services.auto_paper_trader.OptionContractService")
    @patch("services.auto_paper_trader.Database")
    def test_rejected_candle_returns_complete_attempt_audit(self, database_type, service_type, build_capture, decision_type, analyze_chain, evaluate_strategy):
        database_type.return_value.paper_trade_progress.return_value = {
            "trades": 0, "days": 0, "open_trades": 0, "target_hits": 0, "stoploss_hits": 0,
        }
        service_type.return_value.get_front_month_future.return_value = {
            "exchange": "NFO", "token": "future", "symbol": "NIFTY-AUG-FUT",
        }
        service_type.return_value.get_contracts.return_value = [
            {"exchange": "NFO", "token": "ce", "symbol": "NIFTYCE", "strike": 25000, "option_type": "CE", "expiry": "2026-08-27", "lot_size": 75},
        ]
        capture = {
            "open": "25000.00", "high": "25020.00", "low": "24980.00", "close": "25010.00",
            "ema_5": "25005.00", "ema_20": "24995.00", "ema_50": "24950.00", "vwap": "25000.00",
            "supertrend": "24990.00", "rsi_14": "55.00", "atr_14": "30.00", "volume": "1000.00",
            "volume_ema": "900.00", "volume_ratio": "1.11", "candle_direction": "BULLISH",
            "fake_breakout_risk": True,
        }
        build_capture.return_value = capture
        decision_type.return_value.evaluate.return_value = {
            "trade_ready": False, "decision": "NO TRADE", "score": 90, "direction": "BULLISH",
            "volume_confirmed": False, "reasons": ["EMA aligned"], "warnings": ["Volume below threshold"],
        }
        analyze_chain.return_value = {"pcr_oi": 1.0, "pcr_volume": 1.0, "quote_rows": [], "call_resistance": 25100, "put_support": 24900}
        evaluate_strategy.return_value = {
            "score": 67, "direction": "BULLISH", "candidate": "CE", "decision": "NO TRADE", "trade_ready": False,
            "passed": 4, "confirmations": [
                {"name": "Directional volume", "passed": False, "detail": "1.11x Volume EMA 20"},
            ],
            "blockers": ["Strong directional volume confirmation is missing"],
        }
        candles = [{"time": "2026-08-04T11:10:00+05:30"}] * 51
        client = unittest.mock.Mock()
        client.get_recent_candles.return_value = candles
        client.get_option_quote.return_value = {"ltp": 25010}
        client.get_option_chain_quotes.return_value = []

        result = run_auto_paper_cycle(client, "NIFTY", {"max_trades_per_day": 5})

        attempt = result["attempt"]
        self.assertEqual(attempt["candle_time"], "2026-08-04T11:10:00+05:30")
        self.assertEqual(attempt["future_symbol"], "NIFTY-AUG-FUT")
        self.assertEqual(attempt["chart"]["score"], 67)
        self.assertEqual(attempt["capture"]["volume_ratio"], "1.11")
        self.assertTrue(any("directional volume" in reason.lower() for reason in attempt["blockers"]))
