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
