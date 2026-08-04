import unittest
from unittest.mock import patch

from engine.full_day_audit import audit_tps_day, format_tps_day_audit


class FullDayAuditTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {"time": f"2026-08-03T{9 + (i // 12):02d}:{(i % 12) * 5:02d}:00+05:30", "open": 100, "high": 102, "low": 98, "close": 100, "volume": 100}
            for i in range(50)
        ]
        self.candles.append({"time": "2026-08-04T09:15:00+05:30", "open": 100, "high": 102, "low": 98, "close": 99, "volume": 200})
        self.candles.append({"time": "2026-08-04T09:20:00+05:30", "open": 99, "high": 100, "low": 95, "close": 96, "volume": 200})
        self.snapshots = [{
            "captured_at": "2026-08-04T09:20", "symbol": "NIFTY", "timeframe": "5m",
            "oi_pcr": 0.8, "volume_pcr": 1.2, "put_support": 95, "call_resistance": 105,
        }]

    @patch("engine.full_day_audit.build_live_capture", return_value={"close": "99", "atr_14": "2"})
    @patch("engine.full_day_audit.evaluate_tps_entry_v2")
    def test_audit_matches_only_same_minute_oi_without_lookahead(self, evaluate, _capture):
        evaluate.return_value = {"trade_ready": False, "passed": 4, "direction": "BEARISH", "candidate": "PE", "blockers": ["Low volume"]}
        result = audit_tps_day(self.candles, self.snapshots, "NIFTY", "04-08-2026")
        self.assertEqual(result["evaluated"], 2)
        self.assertEqual(result["oi_matched"], 1)
        self.assertIsNotNone(evaluate.call_args_list[0].args[2]["pcr_oi"])
        self.assertIsNone(evaluate.call_args_list[1].args[2]["pcr_oi"])
        self.assertIn("No strict setup found", format_tps_day_audit(result))


if __name__ == "__main__":
    unittest.main()
