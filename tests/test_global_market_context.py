import unittest

from services.global_market_context import parse_gift_nifty


class GlobalContextTests(unittest.TestCase):
    def test_parses_official_gift_future_fields(self):
        result = parse_gift_nifty({"data": [{"LASTPRICE": "25,100.50", "PREVCLOSE": "25,000.00",
                                             "DAYOPEN": "25,020", "DAYHIGH": "25,130", "DAYLOW": "24,980",
                                             "EXPIRY": "27-Aug-2026"}]})
        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["change_percent"], .402, places=3)
        self.assertEqual(result["source"], "NSE IX official")

    def test_empty_official_response_is_never_invented(self):
        result = parse_gift_nifty({"data": []})
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
