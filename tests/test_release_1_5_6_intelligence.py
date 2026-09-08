import unittest

from engine.index_candle_analysis_engine import multi_candle_regime
from engine.oi_flow_intelligence import analyze_oi_flow, reconstruct_oi_change
from ui.pages.strategy_trades_page import strategy_regime_track


class Release156IntelligenceTests(unittest.TestCase):
    def test_exact_contract_oi_delta_is_reconstructed(self):
        previous = [
            {"strike": 24000, "option_type": "CE", "oi": 100},
            {"strike": 24000, "option_type": "PE", "oi": 200},
        ]
        current = [
            {"strike": 24000, "option_type": "CE", "oi": 125, "oi_change": 0},
            {"strike": 24000, "option_type": "PE", "oi": 190, "oi_change": 0},
        ]
        rows, source, coverage = reconstruct_oi_change(current, previous)
        self.assertEqual(source, "LOCAL SNAPSHOT DELTA")
        self.assertEqual(coverage, 100)
        self.assertEqual(rows[0]["oi_change"], 25)
        self.assertEqual(rows[1]["oi_change"], -10)

    def test_no_previous_surface_remains_data_gap(self):
        rows = [
            {"strike": 24000, "option_type": "CE", "oi": 100, "oi_change": 0, "volume": 20},
            {"strike": 24000, "option_type": "PE", "oi": 100, "oi_change": 0, "volume": 20},
        ]
        result = analyze_oi_flow(rows, 24000)
        self.assertEqual(result["direction"], "DATA GAP")
        self.assertEqual(result["coi_source"], "UNAVAILABLE")

    def test_multi_candle_regime_uses_three_horizons(self):
        candles = []
        for index in range(12):
            opening = 100 + index * 2
            candles.append({"open": opening, "high": opening + 3, "low": opening - 1, "close": opening + 2})
        result = multi_candle_regime(candles)
        self.assertEqual(result["regime"], "BULLISH")
        self.assertEqual(set(result["horizons"]), {"3", "6", "12"})

    def test_opposite_direction_strategy_is_shadow_only(self):
        self.assertEqual(strategy_regime_track({"bias": "BULLISH"}, "BEARISH"), "SHADOW_ONLY")
        self.assertEqual(strategy_regime_track({"bias": "BEARISH"}, "BEARISH"), "PRIMARY")


if __name__ == "__main__":
    unittest.main()
