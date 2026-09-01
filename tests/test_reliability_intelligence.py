from datetime import datetime, timedelta

from core.database_manager import Database
from engine.three_pm_research_engine import evaluate_three_pm_shadow
from services.market_data_hub import MarketDataHub
from services.reliability_intelligence import (
    broker_freshness, data_quality_gate, execution_quality, score_calibration,
    shadow_eligibility, strategy_portfolio_risk,
)


def test_data_quality_gate_blocks_open_session_without_verified_sources():
    result = data_quality_gate(
        connected=False, market_state="OPEN", hub_health={"state": "WAITING"},
        broker_health={"requests": 0, "success_rate": 0},
    )
    assert result["status"] == "BLOCK"
    assert not result["order_ready"]


def test_market_data_execution_gate_detects_stale_snapshot(monkeypatch):
    monkeypatch.setattr(MarketDataHub, "health", classmethod(lambda cls: {
        "state": "READY", "last_success_at": (datetime.now() - timedelta(seconds=30)).isoformat(),
    }))
    result = MarketDataHub.execution_gate(15)
    assert not result["allowed"]
    assert "stale" in result["reasons"][0].lower()


def test_execution_fill_migration_and_slippage_measurement(tmp_path):
    db = Database(tmp_path / "quality.db")
    order = {"exchange": "NFO", "symbol_token": "1", "trading_symbol": "NIFTYCE", "side": "BUY",
             "quantity": 10, "limit_price": 100}
    audit_id = db.create_execution_audit(order, "fp", "ACCEPTED_NOT_FILLED")
    db.update_execution_fill(audit_id, status="FILLED", average_fill_price=101, filled_quantity=10)
    result = execution_quality(db)
    assert result["slippage_status"] == "MEASURED"
    assert result["average_slippage"] == 10


def test_shadow_mode_stays_paper_only_without_30_outcomes(tmp_path):
    result = shadow_eligibility(Database(tmp_path / "shadow.db"))
    assert not result["eligible"]
    assert result["state"] == "SHADOW / PAPER ONLY"


def test_three_pm_shadow_requires_confluence_not_price_alone():
    watch = evaluate_three_pm_shadow([{
        "premium": 60, "premium_change_pct": 45, "option_type": "PE",
        "source_completeness": "PARTIAL", "contract_symbol": "NIFTYPE",
    }], spot_move=-20, spot_reference=24000)
    assert watch["state"] == "WATCH"
    candidate = evaluate_three_pm_shadow([{
        "premium": 60, "premium_change_pct": 45, "volume_ratio": 3,
        "oi_change_pct": 5, "option_type": "PE", "source_completeness": "COMPLETE",
        "contract_symbol": "NIFTYPE",
    }], spot_move=-20, spot_reference=24000)
    assert candidate["state"] == "SHADOW CANDIDATE"
    assert candidate["side"] == "PE"


def test_broker_success_is_not_freshness_success(tmp_path):
    db = Database(tmp_path / "freshness.db")
    for age in (30, 90, 900):
        db.save_broker_telemetry({
            "provider": "TEST", "operation": "candles", "started_at": "2026-09-01T10:00:00",
            "completed_at": "2026-09-01T10:00:01", "duration_ms": 100 + age,
            "outcome": "SUCCESS", "attempt_count": 1, "cache_hit": False,
            "data_timestamp": "x", "data_age_seconds": age, "details": {},
        })
    result = broker_freshness(db, stale_seconds=300)
    assert result["provider_success"] == 3
    assert result["fresh_success"] == 2
    assert result["stale_success"] == 1
    assert result["status"] == "DEGRADED"


def test_strategy_portfolio_groups_correlated_variants(tmp_path):
    db = Database(tmp_path / "portfolio.db")
    candidate = {
        "strategy": "Bull Call Debit Spread", "friendly_name": "Cutie", "family": "DIRECTIONAL",
        "bias": "BULLISH", "legs": [{"action": "BUY", "option_type": "CE", "strike": 100, "lots": 1}],
        "max_profit": 100, "max_loss": 50, "capital_required": 50, "entry_cashflow": -50,
        "return_on_capital": 20, "breakevens": [105], "profit_zone": "ABOVE", "scenario_profitable_percent": 60,
        "rank_score": 70, "explanation": "test",
    }
    for minute in (30, 35):
        trade_id = db.save_strategy_trade(candidate, {"symbol": "NIFTY", "spot": 100, "expiry": "TEST", "candle_time": f"2026-09-01T09:{minute}:00"})
        db.cursor.execute("UPDATE strategy_trades SET trade_date='01-09-2026',status='CLOSED',realized_pnl=10 WHERE id=?", (trade_id,))
    db.connection.commit()
    result = strategy_portfolio_risk(db, "01-09-2026")
    assert result["variants"] == 2
    assert len(result["groups"]) == 1
    assert result["groups"][0]["maximum_defined_loss"] == 100


def test_score_calibration_uses_only_closed_linked_outcomes(tmp_path):
    db = Database(tmp_path / "calibration.db")
    # No linked closed paper outcomes means the score remains explicitly uncalibrated.
    assert score_calibration(db) == []
