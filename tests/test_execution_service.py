from datetime import datetime

import pytest

from core.database_manager import Database
from services.execution_service import ExecutionService, OrderRequest


class FakeSettings:
    def __init__(self, enabled=True, mode="REAL"):
        self.values = {
            "real_execution_enabled": enabled,
            "limited_real_pilot_enabled": True,
            "real_pilot_max_orders": 2,
            "real_pilot_max_quantity": 65,
            "real_pilot_risk_percent": .25,
            "real_pilot_daily_loss_percent": .5,
            "capital": 100000,
            "execution_mode": mode,
            "execution_max_orders_per_day": 3,
            "execution_max_quantity": 65,
            "execution_max_order_value": 25_000.0,
            "execution_max_daily_loss": 1_000.0,
            "execution_duplicate_window_seconds": 120,
        }

    def load(self):
        return dict(self.values)


class FakeDatabase:
    def __init__(self):
        self.rows = []

    def count_execution_orders(self, _day):
        return sum(row["status"] not in {"BLOCKED", "REJECTED"} for row in self.rows)

    def execution_loss_today(self, _day):
        return 0.0

    def has_recent_execution_fingerprint(self, fingerprint, _seconds):
        return any(row["fingerprint"] == fingerprint and row["status"] not in {"BLOCKED", "REJECTED"} for row in self.rows)

    def create_execution_audit(self, order, fingerprint, status, message=""):
        self.rows.append({"id": len(self.rows) + 1, "fingerprint": fingerprint, "status": status,
                          "broker_order_id": "", "message": message, **order})
        return len(self.rows)

    def update_execution_audit(self, audit_id, status, broker_order_id="", message=""):
        self.rows[audit_id - 1].update(status=status, broker_order_id=broker_order_id, message=message)

    def get_execution_audit(self, audit_id):
        return self.rows[audit_id - 1]


class FakeClient:
    def place_limit_order(self, _order):
        return {"order_id": "OID-1", "unique_order_id": "UID-1"}

    def get_order_book(self):
        return [{"orderid": "OID-1", "status": "complete"}]


class UncertainClient:
    def place_limit_order(self, _order):
        raise RuntimeError("network timeout")


class FakeLiveSession:
    broker_id = "angel_one"
    client = FakeClient()

    @classmethod
    def connected(cls):
        return True


def order(**changes):
    values = dict(exchange="NFO", symbol_token="123", trading_symbol="NIFTYOPT", side="BUY",
                  quantity=25, limit_price=100.0, product_type="INTRADAY", target_price=105.0, stop_price=95.0)
    values.update(changes)
    return OrderRequest(**values)


def open_market(monkeypatch):
    monkeypatch.setattr("services.execution_service.market_session", lambda settings: {"state": "OPEN"})


def test_execution_defaults_to_locked_and_requires_saved_opt_in(monkeypatch):
    open_market(monkeypatch)
    service = ExecutionService(FakeDatabase(), FakeSettings(enabled=False), FakeLiveSession)
    with pytest.raises(RuntimeError, match="disabled"):
        service.arm("ENABLE REAL TRADING")
    assert service.validate(order(), "PLACE LIMIT ORDER")[0] == "Execution session is locked"


def test_submit_is_explicit_audited_and_duplicate_protected(monkeypatch):
    open_market(monkeypatch)
    database = FakeDatabase()
    service = ExecutionService(database, FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    result = service.submit(order(), "PLACE LIMIT ORDER")
    assert result["status"] == "ACCEPTED_NOT_FILLED"
    assert database.rows[0]["broker_order_id"] == "OID-1"
    service.disarm()
    service.arm("ENABLE REAL TRADING")
    with pytest.raises(RuntimeError, match="Duplicate order blocked"):
        service.submit(order(), "PLACE LIMIT ORDER")


def test_market_hours_caps_and_identity_are_fail_closed(monkeypatch):
    monkeypatch.setattr("services.execution_service.market_session", lambda settings: {"state": "CLOSED"})
    service = ExecutionService(FakeDatabase(), FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    failures = service.validate(order(symbol_token="", trading_symbol="", quantity=66), "wrong")
    assert "Regular market session is not open" in failures
    assert "Symbol token is required" in failures
    assert "Trading symbol is required" in failures
    assert "Quantity exceeds safety cap" in failures
    assert "Final confirmation phrase is missing" in failures


def test_limited_pilot_rejects_trade_risk_above_quarter_percent(monkeypatch):
    open_market(monkeypatch)
    service = ExecutionService(FakeDatabase(), FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    failures = service.validate(order(quantity=65, stop_price=90), "PLACE LIMIT ORDER")
    assert any("Pilot trade risk" in failure for failure in failures)


def test_refresh_status_keeps_broker_fill_state_distinct(monkeypatch):
    open_market(monkeypatch)
    database = FakeDatabase()
    service = ExecutionService(database, FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    result = service.submit(order(), "PLACE LIMIT ORDER")
    row = service.refresh_status(result["audit_id"])
    assert row["status"] == "complete"
    assert database.rows[0]["status"] == "COMPLETE"


def test_uncertain_submission_stays_duplicate_blocked(monkeypatch):
    open_market(monkeypatch)
    database = FakeDatabase()
    live = FakeLiveSession()
    live.client = UncertainClient()
    service = ExecutionService(database, FakeSettings(), live)
    service.arm("ENABLE REAL TRADING")
    with pytest.raises(RuntimeError, match="network timeout"):
        service.submit(order(), "PLACE LIMIT ORDER")
    assert database.rows[0]["status"] == "SUBMISSION_UNKNOWN"
    service.disarm()
    service.arm("ENABLE REAL TRADING")
    with pytest.raises(RuntimeError, match="Duplicate order blocked"):
        service.submit(order(), "PLACE LIMIT ORDER")


def test_execution_audit_schema_is_upgrade_safe(tmp_path):
    database = Database(tmp_path / "test.db")
    columns = {row["name"] for row in database.cursor.execute("PRAGMA table_info(execution_audit)")}
    assert {"fingerprint", "broker_order_id", "realized_pnl", "status"} <= columns
    database.connection.close()


def test_paper_plan_is_saved_without_broker_connection():
    database = FakeDatabase()
    service = ExecutionService(database, FakeSettings(enabled=False, mode="PAPER"), FakeLiveSession)
    planned = order(target_price=120.0, stop_price=90.0, time_exit="15:20")
    result = service.stage_paper(planned)
    assert result["status"] == "PAPER_PLAN"
    assert database.rows[0]["status"] == "PAPER_PLAN"
    assert database.rows[0]["target_price"] == 120.0
    assert database.rows[0]["stop_price"] == 90.0


@pytest.mark.parametrize(
    "side,basis,value,purpose,expected",
    [("BUY", "PERCENT", 20, "TARGET", 120.0), ("BUY", "AMOUNT", 10, "STOP", 90.0),
     ("SELL", "PERCENT", 20, "TARGET", 80.0), ("SELL", "AMOUNT", 10, "STOP", 110.0)],
)
def test_planned_exit_price_supports_amount_and_percentage(side, basis, value, purpose, expected):
    assert ExecutionService.exit_price(100, side, basis, value, purpose) == expected
