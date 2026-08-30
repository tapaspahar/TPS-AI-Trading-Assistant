import unittest
from datetime import date, datetime, time, timedelta, timezone

from engine.expiry_spike_engine import evaluate_spike, predict_expiry_spike, select_nearby_expiry_contracts
from ui.pages.expiry_observation_page import cas_context, expiry_monitor_window, select_atm_parity_pair


class ExpirySpikeEngineTests(unittest.TestCase):
    def test_atm_parity_uses_closest_strike_and_ten_point_boundary(self):
        pairs = {
            24350.0: {"CE": {"premium": 50}, "PE": {"premium": 50}},
            24400.0: {"CE": {"premium": 42}, "PE": {"premium": 52}},
        }
        result = select_atm_parity_pair(pairs, 24392)
        self.assertEqual(result["strike"], 24400.0)
        self.assertEqual(result["gap"], 10.0)

    def test_atm_parity_does_not_choose_farther_match_when_atm_gap_is_too_wide(self):
        pairs = {
            24350.0: {"CE": {"premium": 50}, "PE": {"premium": 50}},
            24400.0: {"CE": {"premium": 40}, "PE": {"premium": 51}},
        }
        self.assertIsNone(select_atm_parity_pair(pairs, 24398))

    def test_selects_paired_ce_and_pe_for_each_nearby_expiry_strike(self):
        near, far = date(2026, 8, 27), date(2026, 9, 3)
        contracts = []
        for expiry in (near, far):
            for strike in (24300, 24350, 24400, 24450, 24500):
                for option_type in ("CE", "PE"):
                    contracts.append({"expiry": expiry, "strike": strike, "option_type": option_type,
                                      "symbol": f"NIFTY{strike}{option_type}", "token": f"{expiry}-{strike}-{option_type}",
                                      "exchange": "NFO"})
        selected = select_nearby_expiry_contracts(contracts, 24410)
        self.assertEqual({row["expiry"] for row in selected}, {near})
        self.assertEqual({row["strike"] for row in selected if row["option_type"] == "CE"}, {24300.0, 24350.0, 24400.0, 24450.0, 24500.0})
        self.assertEqual({row["strike"] for row in selected if row["option_type"] == "PE"}, {24300.0, 24350.0, 24400.0, 24450.0, 24500.0})
        self.assertEqual(len(selected), 10)

    def test_price_acceleration_without_independent_evidence_is_watch_only(self):
        start = datetime(2026, 8, 27, 15, 10)
        result = evaluate_spike([
            {"observed_at": start, "premium": 20, "volume": 100, "open_interest": 1000},
            {"observed_at": start + timedelta(minutes=2), "premium": 60, "volume": 110, "open_interest": 1010},
        ])
        self.assertFalse(result["event"])
        self.assertEqual(result["state"], "PRICE WATCH")

    def test_confirmed_acceleration_becomes_spike(self):
        start = datetime(2026, 8, 27, 15, 10)
        result = evaluate_spike([
            {"observed_at": start, "premium": 20, "volume": 100, "open_interest": 1000},
            {"observed_at": start + timedelta(minutes=1), "premium": 25, "volume": 110, "open_interest": 1010},
            {"observed_at": start + timedelta(minutes=2), "premium": 60, "volume": 160, "open_interest": 1060},
        ])
        self.assertTrue(result["event"])
        self.assertEqual(result["state"], "SPIKE")
        self.assertGreaterEqual(result["premium_change_pct"], 40)
        self.assertTrue(result["confirmations"])

    def test_monitor_only_runs_after_three_on_actual_expiry(self):
        tz = timezone(timedelta(hours=5, minutes=30))
        expiry = date(2026, 8, 27)
        self.assertEqual(expiry_monitor_window(datetime(2026, 8, 27, 14, 59, tzinfo=tz), True, expiry, time(15, 30)), "ARMED UNTIL 3:00 PM")
        self.assertEqual(expiry_monitor_window(datetime(2026, 8, 27, 15, 1, tzinfo=tz), True, expiry, time(15, 30)), "MONITORING")
        self.assertEqual(expiry_monitor_window(datetime(2026, 8, 27, 15, 31, tzinfo=tz), True, expiry, time(15, 30)), "MARKET CLOSED")
        self.assertEqual(expiry_monitor_window(datetime(2026, 8, 26, 15, 1, tzinfo=tz), True, expiry, time(15, 30)), "NOT EXPIRY")

    def test_cas_is_context_not_an_option_market_halt(self):
        tz = timezone(timedelta(hours=5, minutes=30))
        message = cas_context(datetime(2026, 8, 27, 15, 20, tzinfo=tz))
        self.assertIn("INDEX OPTIONS CONTINUOUS", message)

    def test_falling_expiry_session_predicts_pe_watch_from_analog_days(self):
        current = [
            {"trade_date": "2026-08-27", "observed_at": "2026-08-27T15:00:00", "spot": 24500},
            {"trade_date": "2026-08-27", "observed_at": "2026-08-27T15:10:00", "spot": 24450},
        ]
        historical = []
        events = []
        for day in ("2026-08-06", "2026-08-13", "2026-08-20"):
            historical.extend([
                {"trade_date": day, "observed_at": day + "T15:00:00", "spot": 24500},
                {"trade_date": day, "observed_at": day + "T15:20:00", "spot": 24440},
            ])
            events.append({"trade_date": day, "option_type": "PE"})
        result = predict_expiry_spike(current, historical, events)
        self.assertEqual(result["side"], "PE")
        self.assertEqual(result["samples"], 3)
        self.assertEqual(result["hits"], 3)
        self.assertIn("Research prediction", result["text"])


if __name__ == "__main__":
    unittest.main()
