import unittest

from engine.option_chain_engine import analyze_option_chain


class OptionChainEngineTests(unittest.TestCase):
    def test_calculates_pcr_and_oi_walls(self):
        contracts = [
            {"token": "1", "strike": 25000, "option_type": "CE"},
            {"token": "2", "strike": 25100, "option_type": "CE"},
            {"token": "3", "strike": 25000, "option_type": "PE"},
            {"token": "4", "strike": 24900, "option_type": "PE"},
        ]
        quotes = [
            {"symbolToken": "1", "opnInterest": 100, "tradeVolume": 10, "ltp": 50},
            {"symbolToken": "2", "opnInterest": 200, "tradeVolume": 10, "ltp": 30},
            {"symbolToken": "3", "opnInterest": 300, "tradeVolume": 20, "ltp": 40},
            {"symbolToken": "4", "opnInterest": 100, "tradeVolume": 20, "ltp": 20},
        ]
        result = analyze_option_chain(contracts, quotes)
        self.assertEqual(result["call_resistance"], 25100)
        self.assertEqual(result["put_support"], 25000)
        self.assertEqual(result["pcr_oi"], 400 / 300)
        self.assertEqual((result["call_oi"], result["put_oi"]), (300, 400))
        self.assertEqual((result["call_volume"], result["put_volume"]), (20, 40))

    def test_aggregates_exchange_reported_change_in_oi(self):
        contracts = [
            {"token": "ce", "strike": 25000, "option_type": "CE"},
            {"token": "pe", "strike": 25000, "option_type": "PE"},
        ]
        quotes = [
            {"symbolToken": "ce", "opnInterest": 100, "changeinOpenInterest": 12},
            {"symbolToken": "pe", "opnInterest": 150, "changeInOI": 30},
        ]
        result = analyze_option_chain(contracts, quotes)
        self.assertEqual((result["call_oi_change"], result["put_oi_change"]), (12, 30))

    def test_builds_expected_range_max_pain_and_quality_from_live_window(self):
        contracts = [
            {"token": "c99", "strike": 99, "option_type": "CE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
            {"token": "p99", "strike": 99, "option_type": "PE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
            {"token": "c100", "strike": 100, "option_type": "CE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
            {"token": "p100", "strike": 100, "option_type": "PE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
            {"token": "c101", "strike": 101, "option_type": "CE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
            {"token": "p101", "strike": 101, "option_type": "PE", "expiry": __import__("datetime").date.today() + __import__("datetime").timedelta(days=7)},
        ]
        quotes = [
            {"symbolToken": row["token"], "opnInterest": 100 if row["strike"] != 100 else 500,
             "tradeVolume": 50, "ltp": 2 if row["strike"] == 100 else 1,
             "bestBidPrice": 1.9 if row["strike"] == 100 else .9,
             "bestAskPrice": 2.1 if row["strike"] == 100 else 1.1}
            for row in contracts
        ]
        result = analyze_option_chain(contracts, quotes, 100)
        self.assertEqual(result["atm_strike"], 100)
        self.assertEqual(result["expected_move"], 4)
        self.assertEqual((result["expected_low"], result["expected_high"]), (96, 104))
        self.assertEqual(result["focused_max_pain"], 100)
        self.assertEqual(result["data_quality_label"], "STRONG")
