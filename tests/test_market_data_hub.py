import unittest
from unittest.mock import Mock

from services.market_data_hub import MarketDataHub


class MarketDataHubTests(unittest.TestCase):
    def setUp(self):
        MarketDataHub.invalidate()
        MarketDataHub._metrics.update({
            "requests": 0, "hits": 0, "misses": 0, "failures": 0,
            "last_success_at": None, "last_failure_at": None,
            "last_error": "", "last_source_timestamp": None,
        })

    def test_equivalent_candle_request_is_shared(self):
        client = Mock(provider_name="TEST")
        client.get_recent_candles.return_value = [{"time": "2026-09-01T10:00:00+05:30", "close": 1}]
        first = MarketDataHub.candles(client, "NFO", "1")
        second = MarketDataHub.candles(client, "NFO", "1")
        self.assertEqual(first, second)
        client.get_recent_candles.assert_called_once()
        self.assertEqual(MarketDataHub.health()["hit_rate"], 50.0)

    def test_force_bypasses_cache_for_final_capture(self):
        client = Mock(provider_name="TEST")
        client.get_option_quote.side_effect = [{"ltp": 10}, {"ltp": 11}]
        self.assertEqual(MarketDataHub.quote(client, "NFO", "1")["ltp"], 10)
        self.assertEqual(MarketDataHub.quote(client, "NFO", "1", force=True)["ltp"], 11)


if __name__ == "__main__":
    unittest.main()
