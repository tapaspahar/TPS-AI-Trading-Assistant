from engine.adaptive_stop_engine import adaptive_option_stop, index_option_risk_profile


SETTINGS = {
    "adaptive_stop_min_percent": 18,
    "adaptive_stop_max_percent": 35,
    "stop_sweep_buffer_percent": 3,
}
ENVIRONMENT = {"regime": "NORMAL", "stop_atr_multiplier": 1}


def test_each_supported_index_has_an_explicit_profile():
    assert index_option_risk_profile("NIFTY")["target_r"] == 1.50
    assert index_option_risk_profile("BANKNIFTY")["target_r"] == 1.60
    assert index_option_risk_profile("SENSEX")["target_r"] == 1.70


def test_faster_index_options_receive_more_breathing_room():
    nifty = adaptive_option_stop(100, ENVIRONMENT, SETTINGS, 1, "NIFTY")
    bank = adaptive_option_stop(100, ENVIRONMENT, SETTINGS, 1, "BANKNIFTY")
    sensex = adaptive_option_stop(100, ENVIRONMENT, SETTINGS, 1, "SENSEX")
    assert nifty["distance_percent"] < bank["distance_percent"] < sensex["distance_percent"]
    assert nifty["stoploss"] > bank["stoploss"] > sensex["stoploss"]


def test_wider_stop_does_not_cross_profile_cap():
    extreme = {"regime": "EXTREME", "stop_atr_multiplier": 2}
    result = adaptive_option_stop(100, extreme, SETTINGS, 20, "SENSEX")
    assert result["distance_percent"] == 40
    assert result["stoploss"] == 60
