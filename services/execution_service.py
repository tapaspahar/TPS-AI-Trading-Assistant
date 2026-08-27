"""Session-locked, audited broker execution with fail-closed safeguards."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from core.market_session import IST, market_session


@dataclass(frozen=True)
class OrderRequest:
    exchange: str
    symbol_token: str
    trading_symbol: str
    side: str
    quantity: int
    limit_price: float
    product_type: str = "INTRADAY"
    target_price: float = 0.0
    stop_price: float = 0.0
    time_exit: str = ""


class ExecutionService:
    UNLOCK_PHRASE = "ENABLE REAL TRADING"

    def __init__(self, database, settings_store, live_session):
        self.database = database
        self.settings_store = settings_store
        self.live_session = live_session
        self._armed = False
        self._kill_switch = False

    @property
    def armed(self):
        return self._armed and not self._kill_switch

    def arm(self, phrase: str):
        if phrase.strip().upper() != self.UNLOCK_PHRASE:
            raise ValueError(f'Type exactly: {self.UNLOCK_PHRASE}')
        settings = self.settings_store.load()
        if str(settings.get("execution_mode", "REAL")).upper() != "REAL":
            raise RuntimeError("Order mode is PAPER. Select REAL in Settings before arming.")
        if not bool(settings.get("real_execution_enabled", False)):
            raise RuntimeError("Real execution is disabled in saved safety settings.")
        self._kill_switch = False
        self._armed = True

    def disarm(self):
        self._armed = False

    def emergency_stop(self):
        self._kill_switch = True
        self._armed = False

    @staticmethod
    def fingerprint(order: OrderRequest) -> str:
        raw = f"{order.exchange}|{order.symbol_token}|{order.trading_symbol}|{order.side}|{order.quantity}|{order.limit_price:.2f}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def exit_price(entry: float, side: str, basis: str, value: float, purpose: str) -> float:
        """Calculate a planned exit without submitting a broker-side exit order."""
        entry, value = float(entry), float(value)
        side, basis, purpose = side.upper(), basis.upper(), purpose.upper()
        if entry <= 0 or value <= 0 or side not in {"BUY", "SELL"} or purpose not in {"TARGET", "STOP"}:
            raise ValueError("Entry, side and exit value are invalid.")
        if basis == "PRICE":
            result = value
        else:
            move = value if basis == "AMOUNT" else entry * value / 100.0
            favorable = (side == "BUY" and purpose == "TARGET") or (side == "SELL" and purpose == "STOP")
            result = entry + move if favorable else entry - move
        if result <= 0:
            raise ValueError("Calculated exit price must be positive.")
        if side == "BUY" and ((purpose == "TARGET" and result <= entry) or (purpose == "STOP" and result >= entry)):
            raise ValueError("BUY target must be above entry and stop below entry.")
        if side == "SELL" and ((purpose == "TARGET" and result >= entry) or (purpose == "STOP" and result <= entry)):
            raise ValueError("SELL target must be below entry and stop above entry.")
        return round(result, 2)

    def stage_paper(self, order: OrderRequest) -> dict:
        failures = self.validate_plan(order, require_exits=True)
        audit_id = self.database.create_execution_audit(
            order.__dict__, self.fingerprint(order), "REJECTED" if failures else "PAPER_PLAN", "; ".join(failures)
        )
        if failures:
            raise RuntimeError("; ".join(failures))
        return {"audit_id": audit_id, "status": "PAPER_PLAN"}

    @staticmethod
    def validate_plan(order: OrderRequest, require_exits: bool = False) -> list[str]:
        failures = []
        if not order.trading_symbol.strip(): failures.append("Trading symbol is required")
        if order.side.upper() not in {"BUY", "SELL"}: failures.append("Side must be BUY or SELL")
        if order.quantity <= 0: failures.append("Quantity must be positive")
        if order.limit_price <= 0: failures.append("Entry price must be positive")
        if require_exits and (order.target_price <= 0 or order.stop_price <= 0):
            failures.append("Target and stop must be calculated")
        elif (order.target_price > 0) != (order.stop_price > 0):
            failures.append("Target and stop must both be supplied")
        return failures

    def validate(self, order: OrderRequest, confirmation: str) -> list[str]:
        settings = self.settings_store.load()
        failures = self.validate_plan(order)
        if str(settings.get("execution_mode", "REAL")).upper() != "REAL": failures.append("Order mode is PAPER")
        if not self.armed: failures.append("Execution session is locked")
        if confirmation.strip().upper() != "PLACE LIMIT ORDER": failures.append("Final confirmation phrase is missing")
        if not self.live_session.connected() or self.live_session.broker_id != "angel_one": failures.append("Connected Angel One session required")
        if market_session(settings=settings)["state"] != "OPEN": failures.append("Regular market session is not open")
        if not order.symbol_token.strip(): failures.append("Symbol token is required")
        if not order.trading_symbol.strip(): failures.append("Trading symbol is required")
        if order.side.upper() not in {"BUY", "SELL"}: failures.append("Side must be BUY or SELL")
        if order.exchange.upper() not in {"NSE", "NFO", "BSE", "BFO"}: failures.append("Exchange is unsupported")
        if order.quantity <= 0 or order.quantity > int(settings.get("execution_max_quantity", 65)): failures.append("Quantity exceeds safety cap")
        if order.limit_price <= 0: failures.append("Limit price must be positive")
        if order.quantity * order.limit_price > float(settings.get("execution_max_order_value", 25000)): failures.append("Order value exceeds safety cap")
        day = datetime.now(IST).date().isoformat()
        if self.database.count_execution_orders(day) >= int(settings.get("execution_max_orders_per_day", 3)): failures.append("Daily real-order cap reached")
        max_loss = float(settings.get("execution_max_daily_loss", 1000))
        if max_loss > 0 and self.database.execution_loss_today(day) >= max_loss: failures.append("Daily execution loss lock active")
        if self.database.has_recent_execution_fingerprint(self.fingerprint(order), int(settings.get("execution_duplicate_window_seconds", 120))): failures.append("Duplicate order blocked")
        return failures

    def submit(self, order: OrderRequest, confirmation: str) -> dict:
        failures = self.validate(order, confirmation)
        audit_id = self.database.create_execution_audit(order.__dict__, self.fingerprint(order), "BLOCKED" if failures else "SUBMITTING", "; ".join(failures))
        if failures:
            raise RuntimeError("; ".join(failures))
        try:
            result = self.live_session.client.place_limit_order(order.__dict__)
            order_id = str(result.get("order_id") or "").strip()
            if not order_id:
                self.database.update_execution_audit(
                    audit_id, "SUBMISSION_UNKNOWN", "",
                    "Broker response did not include an order ID; verify the broker order book before retrying",
                )
                raise RuntimeError("Broker response had no order ID. Submission state is UNKNOWN; verify the broker order book before retrying.")
            self.database.update_execution_audit(audit_id, "ACCEPTED_NOT_FILLED", order_id, "Broker accepted request; fill pending verification")
            return {**result, "audit_id": audit_id, "status": "ACCEPTED_NOT_FILLED"}
        except Exception as error:
            current = self.database.get_execution_audit(audit_id)
            if not current or current["status"] != "SUBMISSION_UNKNOWN":
                self.database.update_execution_audit(
                    audit_id, "SUBMISSION_UNKNOWN", "",
                    f"Submission result uncertain: {error}. Verify broker order book before retrying.",
                )
            raise

    def refresh_status(self, audit_id: int) -> dict:
        audit = self.database.get_execution_audit(audit_id)
        if not audit or not audit["broker_order_id"]: raise RuntimeError("No broker order ID is available.")
        rows = self.live_session.client.get_order_book()
        row = next((item for item in rows if str(item.get("orderid") or item.get("orderId")) == str(audit["broker_order_id"])), None)
        if not row: raise RuntimeError("Order is not visible in the broker order book yet.")
        status = str(row.get("status") or row.get("orderstatus") or "UNKNOWN").upper()
        self.database.update_execution_audit(audit_id, status, str(audit["broker_order_id"]), str(row.get("text") or row.get("message") or ""))
        return row
