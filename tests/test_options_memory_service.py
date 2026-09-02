from core.database_manager import Database
from services.options_memory_service import build_options_memory_view, candle_pattern, snapshot_similarity


def row(**changes):
    value = {"open": 100, "high": 112, "low": 98, "close": 110, "direction": "BULLISH",
             "aggression": "BUYERS AGGRESSIVE", "oi_direction": "BULLISH FLOW", "call_coi": -10,
             "put_coi": 30, "volume_ratio": 1.5, "range_ratio": 1.4, "source_completeness": 100}
    value.update(changes); return value


def test_candle_pattern_and_similarity_are_explainable():
    assert candle_pattern(row()) == "BULLISH IMPULSE"
    assert snapshot_similarity(row(), row()) == 100
    assert snapshot_similarity(row(), row(direction="BEARISH", oi_direction="BEARISH FLOW")) < 100


def test_memory_uses_only_prior_day_next_candle_outcomes(tmp_path):
    db = Database(tmp_path / "memory.db")
    for date, times, closes in (("01-09-2026", ("09:15", "09:20"), (110, 120)),
                                ("02-09-2026", ("09:15",), (110,))):
        for time, close in zip(times, closes):
            item = row(close=close, move_points=10, trade_date=date, candle_time=f"2026-09-{date[:2]}T{time}+05:30",
                       analyzed_at=f"2026-09-{date[:2]}T{time}:30+05:30", symbol="NIFTY", state="PRICE + OI ALIGNED",
                       volume=1000, oi_quality=100, call_oi=100, put_oi=120, put_wall=100, put_wall_health="DEFENDED",
                       call_wall=120, call_wall_health="WEAKENING", explanation="test", details_json="{}")
            db.save_index_candle_analysis(item)
    view = build_options_memory_view(db, "NIFTY", "02-09-2026")
    assert len(view["rows"]) == 1
    assert view["analogs"][0]["next_direction"] == "UP"
    assert view["state"] == "LEARNING / LOW CONFIDENCE"
