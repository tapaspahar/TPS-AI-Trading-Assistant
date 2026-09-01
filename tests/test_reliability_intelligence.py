from datetime import datetime, timedelta

from core.database_manager import Database
from engine.three_pm_research_engine import evaluate_three_pm_shadow
from services.market_data_hub import MarketDataHub
from services.reliability_intelligence import data_quality_gate, execution_quality, shadow_eligibility


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
