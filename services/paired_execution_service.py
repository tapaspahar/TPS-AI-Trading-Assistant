"""Safeguarded same-strike CE+PE execution and combined-P&L management."""
from __future__ import annotations

import json
from datetime import datetime

from core.market_session import IST, market_session
from services.execution_service import ExecutionService, OrderRequest


class PairedExecutionService:
    """Manage one long option pair; REAL authorization is deliberately session-only."""

    ARM_PHRASE = "ARM EXPIRY PAIR"

    def __init__(self, database, settings_store, live_session):
        self.database = database
        self.settings_store = settings_store
        self.live_session = live_session
        self.execution = ExecutionService(database, settings_store, live_session)
        self._pair_armed = False

    @property
    def armed(self):
        return self._pair_armed and self.execution.armed

    def arm_real(self, execution_phrase, pair_phrase):
        if pair_phrase.strip().upper() != self.ARM_PHRASE:
            raise ValueError(f"Type exactly: {self.ARM_PHRASE}")
        self.execution.arm(execution_phrase)
        self._pair_armed = True

    def disarm(self):
        self._pair_armed = False
        self.execution.disarm()

    def emergency_stop(self):
        self._pair_armed = False
        self.execution.emergency_stop()

    def open_pair(self, *, underlying, expiry, strike, ce, pe, lots, target_pnl, stop_pnl, time_exit, real=False):
        settings = self.settings_store.load()
        if self.database.get_open_execution_pair(underlying):
            raise RuntimeError(f"{underlying} ka ek paired position already open/pending hai.")
        if market_session(settings=settings)["state"] != "OPEN":
            raise RuntimeError("Regular market session open nahi hai.")
        lots = int(lots); lot_size = int(ce["contract"].get("lot_size") or 0)
        if lots <= 0 or lot_size <= 0 or int(pe["contract"].get("lot_size") or 0) != lot_size:
            raise RuntimeError("Valid and equal CE/PE lot size required hai.")
        quantity = lots * lot_size
        ce_price, pe_price = float(ce["premium"]), float(pe["premium"])
        if min(ce_price, pe_price, float(target_pnl), float(stop_pnl)) <= 0:
            raise RuntimeError("Fresh positive CE/PE prices, target aur maximum loss required hain.")
        try:
            datetime.strptime(str(time_exit), "%H:%M")
        except ValueError as error:
            raise RuntimeError("Time exit valid HH:MM format mein required hai.") from error
        mode = "REAL" if real else "PAPER"
        if real and not self.armed:
            raise RuntimeError("Real expiry pair session armed nahi hai.")
        common = dict(trading_date=datetime.now(IST).date().isoformat(), source_page="EXPIRY_AFTER_3PM",
                      mode=mode, underlying=underlying, strike=float(strike), expiry=str(expiry), lots=lots,
                      quantity=quantity, status="REAL_SUBMITTING" if real else "PAPER_OPEN",
                      ce_symbol=ce["contract"]["symbol"], ce_token=ce["contract"]["token"], ce_entry=ce_price,
                      pe_symbol=pe["contract"]["symbol"], pe_token=pe["contract"]["token"], pe_entry=pe_price,
                      target_pnl=float(target_pnl), stop_pnl=float(stop_pnl), time_exit=str(time_exit),
                      details={"warning": "Long straddle; profit guaranteed nahi hai. IV crush/theta risk active."})
        pair_id = self.database.create_execution_pair(common)
        if not real:
            return {"id": pair_id, "status": "PAPER_OPEN"}
        orders = []
        for leg in (ce, pe):
            contract = leg["contract"]
            orders.append(OrderRequest(
                contract["exchange"], str(contract["token"]), contract["symbol"],
                "BUY", quantity, round(float(leg["premium"]), 2),
                exits_managed_externally=True, managed_risk_amount=float(stop_pnl),
            ))
        # Validate both legs before sending either one. Broker orders are not
        # atomic, so a known failure must be caught before the first leg leaves.
        remaining = int(settings.get("execution_max_orders_per_day", 3)) - self.database.count_execution_orders(
            datetime.now(IST).date().isoformat()
        )
        failures = []
        if remaining < 2:
            failures.append("Daily real-order cap has fewer than two slots remaining")
        for order in orders:
            failures.extend(self.execution.validate(order, "PLACE LIMIT ORDER"))
        if failures:
            self.database.update_execution_pair(pair_id, status="PAIR_PREFLIGHT_BLOCKED",
                                                exit_reason="; ".join(dict.fromkeys(failures)))
            raise RuntimeError("; ".join(dict.fromkeys(failures)))
        submitted = []
        try:
            for order in orders:
                submitted.append(self.execution.submit(order, "PLACE LIMIT ORDER"))
            self.database.update_execution_pair(pair_id, ce_order_id=submitted[0]["order_id"],
                                                pe_order_id=submitted[1]["order_id"])
            return {"id": pair_id, "status": "REAL_SUBMITTING", "orders": submitted}
        except Exception as error:
            # Broker orders are not atomic. Cancel every accepted-but-unverified leg
            # and make the uncertainty explicit; never silently retry a duplicate.
            for result in submitted:
                try: self.live_session.client.cancel_order(result.get("order_id", ""))
                except Exception: pass
            self.database.update_execution_pair(pair_id, status="PAIR_SUBMISSION_FAILED",
                                                exit_reason=f"Partial/failed submission: {error}")
            raise RuntimeError(f"Pair submission incomplete; accepted leg(s) cancel requested. Broker order book verify karein: {error}") from error

    def refresh_real_pair(self, pair):
        """Confirm both entry fills before combined-P&L monitoring starts."""
        if str(pair["mode"]).upper() != "REAL" or str(pair["status"]) != "REAL_SUBMITTING":
            return str(pair["status"])
        rows = self.live_session.client.get_order_book()
        by_id = {str(row.get("orderid") or row.get("orderId") or ""): row for row in rows}
        statuses = []
        for order_id in (pair["ce_order_id"], pair["pe_order_id"]):
            row = by_id.get(str(order_id or ""))
            statuses.append(str((row or {}).get("status") or (row or {}).get("orderstatus") or "PENDING").upper())
        completed = {"COMPLETE", "COMPLETED", "FILLED", "TRADED"}
        failed = {"REJECTED", "CANCELLED", "CANCELED"}
        if all(status in completed for status in statuses):
            self.database.update_execution_pair(pair["id"], status="REAL_OPEN")
            return "REAL_OPEN"
        if any(status in failed for status in statuses):
            # A broker cannot guarantee atomic multi-leg fills. If exactly one leg
            # filled, flatten it immediately; cancel every leg which can still be
            # pending. This reduces naked exposure but cannot remove gap/slippage risk.
            unwind_ids, unwind_errors = [], []
            legs = (
                (pair["ce_symbol"], pair["ce_token"], pair["ce_order_id"], statuses[0]),
                (pair["pe_symbol"], pair["pe_token"], pair["pe_order_id"], statuses[1]),
            )
            for symbol, token, order_id, status in legs:
                try:
                    if status in completed:
                        result = self.live_session.client.place_market_order({
                            "exchange": "BFO" if pair["underlying"] == "SENSEX" else "NFO",
                            "symbol_token": token, "trading_symbol": symbol, "side": "SELL",
                            "quantity": int(pair["quantity"]), "product_type": "INTRADAY",
                        })
                        unwind_ids.append(result.get("order_id", ""))
                    elif status not in failed:
                        self.live_session.client.cancel_order(order_id)
                except Exception as error:
                    unwind_errors.append(f"{symbol}: {error}")
            status = "ENTRY_PARTIAL_EXIT_SUBMITTED" if unwind_ids and not unwind_errors else "ENTRY_ATTENTION_REQUIRED"
            self.database.update_execution_pair(
                pair["id"], status=status,
                exit_reason=f"Entry legs not both filled: CE={statuses[0]}, PE={statuses[1]}",
                details_json=json.dumps({"protective_unwind_order_ids": unwind_ids, "errors": unwind_errors}),
            )
            raise RuntimeError("CE/PE entry legs dono fill nahi hue. Protective unwind/cancel request bheji gayi; broker positions/order book turant verify karein.")
        return "REAL_SUBMITTING"

    def update_from_quotes(self, pair, ce_price, pe_price, now=None):
        now = now or datetime.now(IST)
        if str(pair["status"]) == "REAL_SUBMITTING":
            state = self.refresh_real_pair(pair)
            if state != "REAL_OPEN":
                return {"pnl": float(pair["last_pnl"] or 0), "exit_reason": "", "status": state}
        pnl = ((float(ce_price) - float(pair["ce_entry"])) +
               (float(pe_price) - float(pair["pe_entry"]))) * int(pair["quantity"])
        self.database.update_execution_pair(pair["id"], last_pnl=round(pnl, 2))
        reason = ""
        if pnl >= float(pair["target_pnl"]): reason = "COMBINED TARGET HIT"
        elif pnl <= -float(pair["stop_pnl"]): reason = "COMBINED MAX LOSS HIT"
        elif str(pair["time_exit"]) and now.strftime("%H:%M") >= str(pair["time_exit"]): reason = "TIME EXIT"
        if reason:
            self.close_pair(pair, reason, pnl)
        return {"pnl": round(pnl, 2), "exit_reason": reason}

    def close_pair(self, pair, reason, pnl):
        if str(pair["mode"]).upper() == "PAPER":
            self.database.update_execution_pair(pair["id"], status="PAPER_CLOSED", last_pnl=round(pnl, 2), exit_reason=reason)
            return
        self.database.update_execution_pair(pair["id"], status="EXITING", exit_reason=reason)
        errors, ids = [], []
        for symbol, token in ((pair["ce_symbol"], pair["ce_token"]), (pair["pe_symbol"], pair["pe_token"])):
            try:
                result = self.live_session.client.place_market_order({"exchange": "BFO" if pair["underlying"] == "SENSEX" else "NFO",
                    "symbol_token": token, "trading_symbol": symbol, "side": "SELL", "quantity": int(pair["quantity"]),
                    "product_type": "INTRADAY"})
                ids.append(result.get("order_id", ""))
            except Exception as error: errors.append(f"{symbol}: {error}")
        status = "REAL_EXIT_SUBMITTED" if not errors else "EXIT_ATTENTION_REQUIRED"
        details = json.dumps({"exit_order_ids": ids, "exit_errors": errors})
        self.database.update_execution_pair(pair["id"], status=status, last_pnl=round(pnl, 2),
                                            exit_reason=reason, details_json=details)
        if errors:
            raise RuntimeError("Ek ya adhik exit leg submit nahi hui; broker position turant verify karein. " + "; ".join(errors))
