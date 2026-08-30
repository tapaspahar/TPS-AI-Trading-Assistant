from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.database_manager import Database
from services.paired_execution_service import PairedExecutionService


class Settings:
    def __init__(self, mode="PAPER"):
        self.values = {
            "execution_mode": mode,
            "real_execution_enabled": mode == "REAL",
            "limited_real_pilot_enabled": mode == "REAL",
            "real_pilot_max_orders": 2,
            "real_pilot_max_quantity": 65,
            "real_pilot_risk_percent": .25,
            "real_pilot_daily_loss_percent": .5,
            "capital": 1_000_000,
            "execution_max_orders_per_day": 10,
            "execution_max_quantity": 1000,
            "execution_max_order_value": 1_000_000,
            "execution_max_daily_loss": 10_000,
            "execution_duplicate_window_seconds": 120,
        }

    def load(self):
        return dict(self.values)


class Client:
    def __init__(self, fail_second=False, order_book=None):
        self.fail_second = fail_second
        self.placed = []
        self.cancelled = []
        self.market = []
        self.order_book = order_book

    def place_limit_order(self, order):
        if self.fail_second and len(self.placed) == 1:
            raise RuntimeError("second leg failed")
        self.placed.append(order)
        return {"order_id": f"O{len(self.placed)}"}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)

    def place_market_order(self, order):
        self.market.append(order)
        return {"order_id": f"X{len(self.market)}"}

    def get_order_book(self):
        return self.order_book or [{"orderid": "O1", "status": "complete"}, {"orderid": "O2", "status": "complete"}]


class Session:
    broker_id = "angel_one"

    def __init__(self, client):
        self.client = client

    def connected(self):
        return True


def legs():
    return (
        {"contract": {"exchange": "NFO", "token": "CE1", "symbol": "NIFTYCE", "lot_size": 65}, "premium": 20.0},
        {"contract": {"exchange": "NFO", "token": "PE1", "symbol": "NIFTYPE", "lot_size": 65}, "premium": 30.0},
    )


def service(tmp_path: Path, mode="PAPER", client=None):
    database = Database(tmp_path / "test.db")
    client = client or Client()
    return PairedExecutionService(database, Settings(mode), Session(client)), database, client


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
def test_paper_pair_opens_once_and_combined_target_closes(_session, tmp_path):
    subject, database, _ = service(tmp_path)
    ce, pe = legs()
    result = subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                               lots=1, target_pnl=650, stop_pnl=325, time_exit="15:25")
    assert result["status"] == "PAPER_OPEN"
    with pytest.raises(RuntimeError, match="already open"):
        subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                          lots=1, target_pnl=650, stop_pnl=325, time_exit="15:25")
    pair = database.get_open_execution_pair("NIFTY")
    update = subject.update_from_quotes(pair, 25, 35)
    assert update["pnl"] == 650
    assert update["exit_reason"] == "COMBINED TARGET HIT"
    assert database.get_open_execution_pair("NIFTY") is None


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
def test_paper_pair_combined_loss_closes(_session, tmp_path):
    subject, database, _ = service(tmp_path)
    ce, pe = legs()
    subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                      lots=1, target_pnl=1000, stop_pnl=650, time_exit="15:25")
    pair = database.get_open_execution_pair("NIFTY")
    update = subject.update_from_quotes(pair, 15, 25)
    assert update["pnl"] == -650
    assert update["exit_reason"] == "COMBINED MAX LOSS HIT"


def test_real_pair_needs_both_session_phrases(tmp_path):
    subject, _, _ = service(tmp_path, "REAL")
    with pytest.raises(ValueError, match="ARM EXPIRY PAIR"):
        subject.arm_real("ENABLE REAL TRADING", "wrong")
    subject.arm_real("ENABLE REAL TRADING", "ARM EXPIRY PAIR")
    assert subject.armed
    subject.disarm()
    assert not subject.armed


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
@patch("services.execution_service.market_session", return_value={"state": "OPEN"})
def test_real_pair_partial_submission_requests_cancel(_execution_session, _pair_session, tmp_path):
    client = Client(fail_second=True)
    subject, database, _ = service(tmp_path, "REAL", client)
    subject.arm_real("ENABLE REAL TRADING", "ARM EXPIRY PAIR")
    ce, pe = legs()
    with pytest.raises(RuntimeError, match="Pair submission incomplete"):
        subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                          lots=1, target_pnl=1000, stop_pnl=500, time_exit="15:25", real=True)
    assert client.cancelled == ["O1"]
    assert database.get_open_execution_pair("NIFTY") is None


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
@patch("services.execution_service.market_session", return_value={"state": "OPEN"})
def test_real_pair_waits_for_both_fills_then_exits_both_legs(_execution_session, _pair_session, tmp_path):
    subject, database, client = service(tmp_path, "REAL")
    subject.arm_real("ENABLE REAL TRADING", "ARM EXPIRY PAIR")
    ce, pe = legs()
    subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                      lots=1, target_pnl=650, stop_pnl=500, time_exit="15:25", real=True)
    pair = database.get_open_execution_pair("NIFTY")
    update = subject.update_from_quotes(pair, 25, 35)
    assert update["exit_reason"] == "COMBINED TARGET HIT"
    assert len(client.market) == 2


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
@patch("services.execution_service.market_session", return_value={"state": "OPEN"})
def test_real_pair_flattens_filled_leg_when_other_leg_rejects(_execution_session, _pair_session, tmp_path):
    client = Client(order_book=[{"orderid": "O1", "status": "complete"}, {"orderid": "O2", "status": "rejected"}])
    subject, database, _ = service(tmp_path, "REAL", client)
    subject.arm_real("ENABLE REAL TRADING", "ARM EXPIRY PAIR")
    ce, pe = legs()
    subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                      lots=1, target_pnl=650, stop_pnl=500, time_exit="15:25", real=True)
    pair = database.get_open_execution_pair("NIFTY")
    with pytest.raises(RuntimeError, match="Protective unwind"):
        subject.update_from_quotes(pair, 20, 30)
    assert len(client.market) == 1
    assert client.market[0]["trading_symbol"] == "NIFTYCE"
    assert database.get_open_execution_pair("NIFTY") is None


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
def test_pair_rejects_invalid_time_exit(_session, tmp_path):
    subject, _, _ = service(tmp_path)
    ce, pe = legs()
    with pytest.raises(RuntimeError, match="HH:MM"):
        subject.open_pair(underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
                          lots=1, target_pnl=650, stop_pnl=500, time_exit="25:99")


@patch("services.paired_execution_service.market_session", return_value={"state": "OPEN"})
def test_parity_pair_saves_shared_observation_and_blocks_restart_duplicate(_session, tmp_path):
    subject, database, _ = service(tmp_path)
    ce, pe = legs()
    observed = "2026-08-27T15:04:30+05:30"
    subject.open_pair(
        underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
        lots=1, target_pnl=650, stop_pnl=500, time_exit="15:25",
        source_page="EXPIRY_ATM_PARITY", trigger_type="ATM_PREMIUM_PARITY",
        observed_at=observed, premium_gap=10,
    )
    pair = database.get_open_execution_pair("NIFTY")
    details = __import__("json").loads(pair["details_json"])
    assert details["ce_observed_at"] == observed == details["pe_observed_at"]
    assert details["premium_gap"] == 10.0
    database.update_execution_pair(pair["id"], status="PAPER_CLOSED")
    with pytest.raises(RuntimeError, match="duplicate entry blocked"):
        subject.open_pair(
            underlying="NIFTY", expiry="2026-08-27", strike=24350, ce=ce, pe=pe,
            lots=1, target_pnl=650, stop_pnl=500, time_exit="15:25",
            source_page="EXPIRY_ATM_PARITY", trigger_type="ATM_PREMIUM_PARITY",
            observed_at=observed, premium_gap=10,
        )
