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

    def get_pending_execution_audits(self):
        return [row for row in self.rows if row["status"] in {
            "SUBMITTING", "SUBMISSION_UNKNOWN", "ACCEPTED_NOT_FILLED", "OPEN", "PARTIAL", "PENDING"
        }]


class FakeClient:
    def place_limit_order(self, _order):
        return {"order_id": "OID-1", "unique_order_id": "UID-1"}

    def get_order_book(self):
        return [{"orderid": "OID-1", "status": "complete"}]


class ManagedClient(FakeClient):
    def __init__(self):
        self.orders = [{"orderid": "OID-1", "status": "complete", "averageprice": 100, "filledshares": 25}]
        self.positions = [{"symboltoken": "123", "tradingsymbol": "NIFTY26SEP25000CE", "netqty": 25}]
        self.exit_requests = []

    def get_order_book(self):
        return list(self.orders)

    def get_positions(self):
        return list(self.positions)

    def place_market_order(self, order):
        self.exit_requests.append(order)
        return {"order_id": "EXIT-1"}


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


def test_once_armed_pilot_can_submit_without_per_order_phrase(monkeypatch):
    open_market(monkeypatch)
    service = ExecutionService(FakeDatabase(), FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    result = service.submit_automated_pilot(order())
    assert result["status"] == "ACCEPTED_NOT_FILLED"


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


def test_restart_reconciliation_updates_known_orders_without_unlocking_auto_real(monkeypatch):
    open_market(monkeypatch)
    database = FakeDatabase()
    service = ExecutionService(database, FakeSettings(), FakeLiveSession)
    service.arm("ENABLE REAL TRADING")
    service.submit(order(), "PLACE LIMIT ORDER")
    result = service.reconcile_pending()
    assert result["reconciliation_complete"] is True
    assert result["automatic_real_unlocked"] is False
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
    assert {"fingerprint", "broker_order_id", "realized_pnl", "status", "target_price", "stop_price",
            "product_type", "expiry_date", "exit_order_id", "managed_state", "overnight_state"} <= columns
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


def test_real_filled_carry_reconciles_position_then_trails_and_exits(monkeypatch, tmp_path):
    database = Database(tmp_path / "real-managed.db")
    settings = FakeSettings()
    settings.values.update({"real_managed_exit_enabled": True, "paper_overnight_gap_hold_enabled": True,
                            "market_pre_open_time": "09:00", "market_open_time": "09:15",
                            "market_close_time": "15:30", "news_risk_pause": False})
    client = ManagedClient()
    live = type("ManagedLive", (), {"broker_id": "angel_one", "client": client,
                                     "connected": classmethod(lambda cls: True)})
    request = order(trading_symbol="NIFTY26SEP25000CE", product_type="CARRYFORWARD", target_price=140, stop_price=80,
                    time_exit="15:20", expiry_date="2026-09-24")
    audit_id = database.create_execution_audit(request.__dict__, "managed-fp", "COMPLETE")
    database.update_execution_audit(audit_id, "COMPLETE", "OID-1", "entry filled")
    database.update_execution_fill(audit_id, status="COMPLETE", average_fill_price=100, filled_quantity=25)
    database.save_gap_probability_forecast({
        "forecast_date": "2026-09-03", "target_date": "2026-09-04",
        "generated_at": "2026-09-03T15:40:00+05:30", "symbol": "NIFTY",
        "stage": "3:40 CLOSE CONFIRMATION", "predicted_class": "GAP UP",
        "gap_up_probability": 58, "flat_probability": 25, "gap_down_probability": 17,
        "confidence": 68, "data_quality": 90, "prior_close": 25000, "inputs": {}, "evidence": [],
    })
    service = ExecutionService(database, settings, live)
    monkeypatch.setattr("services.execution_service.MarketDataHub.quote", lambda *args, **kwargs: {"bid": 110})
    assert service.monitor_real_positions(datetime(2026, 9, 3, 15, 22)) == []
    self_row = database.get_execution_audit(audit_id)
    assert self_row["overnight_state"] == "HELD"

    monkeypatch.setattr("services.execution_service.MarketDataHub.quote", lambda *args, **kwargs: {"bid": 150})
    assert service.monitor_real_positions(datetime(2026, 9, 4, 9, 16)) == []
    trailed = database.get_execution_audit(audit_id)
    assert trailed["overnight_state"] == "REVALIDATED"
    assert trailed["target_price"] > 150
    assert trailed["stop_price"] == 140

    monkeypatch.setattr("services.execution_service.MarketDataHub.quote", lambda *args, **kwargs: {"bid": 139})
    events = service.monitor_real_positions(datetime(2026, 9, 4, 9, 17))
    assert events[0]["outcome"] == "REAL STOP HIT EXIT SUBMITTED"
    assert database.get_execution_audit(audit_id)["status"] == "EXIT_SUBMITTED"
    assert client.exit_requests[0]["side"] == "SELL"
    client.orders.append({"orderid": "EXIT-1", "status": "complete", "averageprice": 138, "filledshares": 25})
    client.positions[0]["netqty"] = 0
    confirmed = service.monitor_real_positions(datetime(2026, 9, 4, 9, 18))
    assert confirmed[0]["outcome"] == "REAL EXIT FILL CONFIRMED"
    final = database.get_execution_audit(audit_id)
    assert final["status"] == "REAL_CLOSED"
    assert final["realized_pnl"] == 950
    database.close()


def test_real_manager_never_exits_on_broker_position_mismatch(monkeypatch, tmp_path):
    database = Database(tmp_path / "real-mismatch.db")
    settings = FakeSettings()
    settings.values["real_managed_exit_enabled"] = True
    client = ManagedClient()
    client.positions[0]["netqty"] = 10
    live = type("ManagedLive", (), {"broker_id": "angel_one", "client": client,
                                     "connected": classmethod(lambda cls: True)})
    request = order(target_price=105, stop_price=95, expiry_date="2026-09-24")
    audit_id = database.create_execution_audit(request.__dict__, "mismatch-fp", "COMPLETE")
    database.update_execution_audit(audit_id, "COMPLETE", "OID-1", "entry filled")
    database.update_execution_fill(audit_id, status="COMPLETE", average_fill_price=100, filled_quantity=25)
    monkeypatch.setattr("services.execution_service.MarketDataHub.quote", lambda *args, **kwargs: {"bid": 90})
    assert ExecutionService(database, settings, live).monitor_real_positions(datetime(2026, 9, 3, 12, 0)) == []
    row = database.get_execution_audit(audit_id)
    assert row["managed_state"] == "POSITION_MISMATCH"
    assert client.exit_requests == []
    database.close()


@pytest.mark.parametrize(
    "side,basis,value,purpose,expected",
    [("BUY", "PERCENT", 20, "TARGET", 120.0), ("BUY", "AMOUNT", 10, "STOP", 90.0),
     ("SELL", "PERCENT", 20, "TARGET", 80.0), ("SELL", "AMOUNT", 10, "STOP", 110.0)],
)
def test_planned_exit_price_supports_amount_and_percentage(side, basis, value, purpose, expected):
    assert ExecutionService.exit_price(100, side, basis, value, purpose) == expected
