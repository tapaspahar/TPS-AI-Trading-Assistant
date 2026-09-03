"""Session-locked, audited broker execution with fail-closed safeguards."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from core.market_session import IST, market_session
from services.market_data_hub import MarketDataHub
from services.reliability_intelligence import shadow_eligibility


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
    exits_managed_externally: bool = False
    managed_risk_amount: float = 0.0
    expiry_date: str = ""


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
        if not bool(settings.get("limited_real_pilot_enabled", False)):
            raise RuntimeError("Enable Limited REAL Pilot Mode before arming a real-money session.")
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
        failures = self.validate_plan(order, require_exits=not order.exits_managed_externally)
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
        failures = self.validate_plan(order, require_exits=not order.exits_managed_externally)
        pilot = bool(settings.get("limited_real_pilot_enabled", False))
        if str(settings.get("execution_mode", "REAL")).upper() != "REAL": failures.append("Order mode is PAPER")
        if not self.armed: failures.append("Execution session is locked")
        if confirmation.strip().upper() != "PLACE LIMIT ORDER": failures.append("Final confirmation phrase is missing")
        if not self.live_session.connected() or self.live_session.broker_id != "angel_one": failures.append("Connected Angel One session required")
        if market_session(settings=settings)["state"] != "OPEN": failures.append("Regular market session is not open")
        if bool(settings.get("execution_require_live_data_gate", False)):
            data_gate = MarketDataHub.execution_gate(15)
            failures.extend(data_gate["reasons"])
        if bool(settings.get("real_require_shadow_eligibility", False)):
            shadow = shadow_eligibility(self.database)
            if not shadow["eligible"]:
                failures.append(
                    f"Shadow validation not eligible: {shadow['samples']}/30 samples, "
                    f"95% lower confidence {shadow['wilson_lower_bound']:.1f}%"
                )
        if not order.symbol_token.strip(): failures.append("Symbol token is required")
        if not order.trading_symbol.strip(): failures.append("Trading symbol is required")
        if order.side.upper() not in {"BUY", "SELL"}: failures.append("Side must be BUY or SELL")
        if order.exchange.upper() not in {"NSE", "NFO", "BSE", "BFO"}: failures.append("Exchange is unsupported")
        quantity_cap = int(settings.get("execution_max_quantity", 65))
        if pilot: quantity_cap = min(quantity_cap, int(settings.get("real_pilot_max_quantity", 65)))
        if order.quantity <= 0 or order.quantity > quantity_cap: failures.append("Quantity exceeds safety cap")
        if order.limit_price <= 0: failures.append("Limit price must be positive")
        if order.quantity * order.limit_price > float(settings.get("execution_max_order_value", 25000)): failures.append("Order value exceeds safety cap")
        day = datetime.now(IST).date().isoformat()
        order_cap = int(settings.get("execution_max_orders_per_day", 3))
        if pilot: order_cap = min(order_cap, int(settings.get("real_pilot_max_orders", 2)))
        if self.database.count_execution_orders(day) >= order_cap: failures.append("Daily real-order cap reached")
        max_loss = float(settings.get("execution_max_daily_loss", 1000))
        if pilot:
            capital = float(settings.get("capital", 100000))
            max_loss = min(max_loss, capital * float(settings.get("real_pilot_daily_loss_percent", .5)) / 100.0)
            trade_risk = (
                float(order.managed_risk_amount) if order.exits_managed_externally
                else abs(float(order.limit_price) - float(order.stop_price)) * int(order.quantity)
            )
            trade_cap = capital * float(settings.get("real_pilot_risk_percent", .25)) / 100.0
            if trade_risk > trade_cap: failures.append(f"Pilot trade risk ₹{trade_risk:,.2f} exceeds ₹{trade_cap:,.2f} cap")
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

    def submit_automated_pilot(self, order: OrderRequest) -> dict:
        """Submit from a once-armed pilot session; all normal validations remain active."""
        if not self.armed:
            raise RuntimeError("Limited REAL pilot session is not armed.")
        settings = self.settings_store.load()
        if not bool(settings.get("limited_real_pilot_enabled", False)):
            raise RuntimeError("Limited REAL Pilot Mode is disabled.")
        return self.submit(order, "PLACE LIMIT ORDER")

    def refresh_status(self, audit_id: int) -> dict:
        audit = self.database.get_execution_audit(audit_id)
        if not audit or not audit["broker_order_id"]: raise RuntimeError("No broker order ID is available.")
        rows = self.live_session.client.get_order_book()
        row = next((item for item in rows if str(item.get("orderid") or item.get("orderId")) == str(audit["broker_order_id"])), None)
        if not row: raise RuntimeError("Order is not visible in the broker order book yet.")
        status = str(row.get("status") or row.get("orderstatus") or "UNKNOWN").upper()
        average = row.get("averageprice") or row.get("averagePrice") or row.get("avgPrice")
        filled = row.get("filledshares") or row.get("filledQuantity") or row.get("filledqty")
        if average not in (None, "") or filled not in (None, ""):
            self.database.update_execution_fill(
                audit_id, status=status, average_fill_price=float(average or 0) or None,
                filled_quantity=int(float(filled or 0)) or None,
                message=str(row.get("text") or row.get("message") or "Broker fill reconciled"),
            )
        else:
            self.database.update_execution_audit(audit_id, status, str(audit["broker_order_id"]), str(row.get("text") or row.get("message") or ""))
        return row

    def reconcile_pending(self) -> dict:
        """Reconcile restart-surviving order intents without guessing fills."""
        if not self.live_session.connected() or self.live_session.broker_id != "angel_one":
            raise RuntimeError("Connected Angel One session required for reconciliation.")
        pending = list(self.database.get_pending_execution_audits())
        order_book = list(self.live_session.client.get_order_book())
        by_id = {
            str(item.get("orderid") or item.get("orderId") or ""): item
            for item in order_book if item.get("orderid") or item.get("orderId")
        }
        updated, unresolved = [], []
        for audit in pending:
            order_id = str(audit["broker_order_id"] or "")
            row = by_id.get(order_id) if order_id else None
            if not row:
                unresolved.append(int(audit["id"]))
                continue
            status = str(row.get("status") or row.get("orderstatus") or "UNKNOWN").upper()
            message = str(row.get("text") or row.get("message") or "Reconciled from broker order book")
            average = row.get("averageprice") or row.get("averagePrice") or row.get("avgPrice")
            filled = row.get("filledshares") or row.get("filledQuantity") or row.get("filledqty")
            if average not in (None, "") or filled not in (None, ""):
                self.database.update_execution_fill(
                    int(audit["id"]), status=status, average_fill_price=float(average or 0) or None,
                    filled_quantity=int(float(filled or 0)) or None, message=message,
                )
            else:
                self.database.update_execution_audit(int(audit["id"]), status, order_id, message)
            updated.append({"audit_id": int(audit["id"]), "order_id": order_id, "status": status})
        return {"checked": len(pending), "updated": updated, "unresolved": unresolved,
                "reconciliation_complete": not unresolved and len(updated) == len(pending),
                "automatic_real_unlocked": False}

    @staticmethod
    def _number(row, *keys):
        for key in keys:
            if row.get(key) not in (None, ""):
                try:
                    return float(row[key])
                except (TypeError, ValueError):
                    pass
        return None

    def monitor_real_positions(self, now=None) -> list[dict]:
        """Manage already-filled REAL entries from broker truth; never infer a position."""
        settings = self.settings_store.load()
        if not settings.get("real_managed_exit_enabled", True):
            return []
        if not self.live_session.connected() or self.live_session.broker_id != "angel_one":
            return []
        now = now or datetime.now(IST)
        now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        audits = list(self.database.get_managed_execution_audits())
        if not audits:
            return []
        try:
            order_book = list(self.live_session.client.get_order_book())
            positions = list(self.live_session.client.get_positions())
        except Exception as error:
            for audit in audits:
                self.database.update_execution_management(
                    int(audit["id"]), managed_state="BROKER_DATA_GAP",
                    message=f"Managed REAL lifecycle paused; broker order/position reconciliation unavailable: {error}",
                )
            return []
        order_by_id = {str(row.get("orderid") or row.get("orderId") or ""): row for row in order_book}
        completed = {"COMPLETE", "COMPLETED", "FILLED", "TRADED"}
        failed = {"REJECTED", "CANCELLED", "CANCELED"}
        events = []
        for audit in audits:
            audit_id = int(audit["id"])
            if str(audit["status"]).upper() == "EXIT_SUBMITTED":
                exit_row = order_by_id.get(str(audit["exit_order_id"] or ""))
                exit_status = str((exit_row or {}).get("status") or (exit_row or {}).get("orderstatus") or "UNKNOWN").upper()
                if exit_status in completed:
                    exit_fill = self._number(exit_row or {}, "averageprice", "averagePrice", "avgPrice")
                    exit_position = next((row for row in positions if
                                         str(row.get("symboltoken") or row.get("symbolToken") or "") == str(audit["symbol_token"])
                                         or str(row.get("tradingsymbol") or row.get("tradingSymbol") or "").upper()
                                         == str(audit["trading_symbol"]).upper()), None)
                    exit_net = self._number(exit_position or {}, "netqty", "netQty", "netQuantity", "net_quantity")
                    if exit_fill and audit["average_fill_price"] and exit_net == 0:
                        sign = 1 if str(audit["side"]).upper() == "BUY" else -1
                        pnl = (exit_fill - float(audit["average_fill_price"])) * int(audit["filled_quantity"] or audit["quantity"]) * sign
                        self.database.update_execution_management(
                            audit_id, status="REAL_CLOSED", managed_state="EXIT_FILL_CONFIRMED",
                            exit_average_fill_price=exit_fill, realized_pnl=round(pnl, 2),
                            message=f"Broker exit fill confirmed at {exit_fill:.2f}; realized gross P&L ₹{pnl:,.2f}.",
                        )
                        events.append({"audit_id": audit_id, "symbol": audit["trading_symbol"],
                                       "outcome": "REAL EXIT FILL CONFIRMED", "ltp": exit_fill})
                    else:
                        self.database.update_execution_management(
                            audit_id, managed_state="EXIT_RECONCILIATION_PENDING",
                            message=f"Exit order reports {exit_status}, but fill price/net-zero broker position is not confirmed (net {exit_net}).",
                        )
                elif exit_status in failed:
                    self.database.update_execution_management(
                        audit_id, status="EXIT_ATTENTION_REQUIRED", managed_state="EXIT_REJECTED",
                        message=f"Broker exit order {audit['exit_order_id']} is {exit_status}; position remains unverified. Manual broker action required.",
                    )
                continue
            position = next((row for row in positions if
                             str(row.get("symboltoken") or row.get("symbolToken") or "") == str(audit["symbol_token"])
                             or str(row.get("tradingsymbol") or row.get("tradingSymbol") or "").upper()
                             == str(audit["trading_symbol"]).upper()), None)
            net_qty = self._number(position or {}, "netqty", "netQty", "netQuantity", "net_quantity")
            expected = int(audit["filled_quantity"] or audit["quantity"])
            expected_signed = expected if str(audit["side"]).upper() == "BUY" else -expected
            if position is None or net_qty is None or int(net_qty) != expected_signed:
                self.database.update_execution_management(
                    audit_id, managed_state="POSITION_MISMATCH",
                    message=f"Expected broker net quantity {expected_signed}; position book showed {net_qty}. No exit order sent.",
                )
                continue
            try:
                quote = MarketDataHub.quote(self.live_session.client, audit["exchange"], audit["symbol_token"],
                                            ttl_seconds=1.0, force=True)
                price = float(quote.get("bid") or quote.get("bestBidPrice") or quote.get("ltp") or 0)
            except Exception as error:
                self.database.update_execution_management(audit_id, managed_state="QUOTE_DATA_GAP", message=str(error))
                continue
            if price <= 0:
                self.database.update_execution_management(audit_id, managed_state="QUOTE_DATA_GAP", message="Executable exit quote unavailable.")
                continue
            side = str(audit["side"]).upper()
            target, stop = float(audit["target_price"]), float(audit["stop_price"])
            session = market_session(now, settings)
            if audit["overnight_state"] == "HELD":
                if session["state"] != "OPEN":
                    continue
                carry = float(audit["overnight_carry_price"] or audit["average_fill_price"] or audit["limit_price"])
                favourable = price > carry if side == "BUY" else price < carry
                if favourable:
                    risk = abs(float(audit["average_fill_price"] or audit["limit_price"]) - stop)
                    gain = abs(price - carry)
                    if side == "BUY":
                        target = max(target, price + min(risk, gain * .35))
                        stop = max(stop, float(audit["average_fill_price"] or audit["limit_price"]), price - min(.5 * risk, gain * .4))
                    else:
                        target = min(target, price - min(risk, gain * .35))
                        stop = min(stop, float(audit["average_fill_price"] or audit["limit_price"]), price + min(.5 * risk, gain * .4))
                    self.database.update_execution_management(
                        audit_id, overnight_state="REVALIDATED", managed_state="REAL_OPEN_MANAGED",
                        target_price=round(target, 2), stop_price=round(stop, 2),
                        message=f"Fresh broker position and opening quote confirmed; target {target:.2f}, trailing stop {stop:.2f}.",
                    )
                else:
                    target = price  # Force a reconciled managed exit below.
            favourable_target = price >= target if side == "BUY" else price <= target
            stop_hit = price <= stop if side == "BUY" else price >= stop
            time_due = bool(audit["time_exit"]) and now.strftime("%H:%M") >= str(audit["time_exit"])
            reason = "TARGET HIT" if favourable_target else "STOP HIT" if stop_hit else "TIME EXIT" if time_due else ""
            if time_due and not (favourable_target or stop_hit) and not audit["overnight_state"]:
                option_type = "CE" if str(audit["trading_symbol"]).upper().endswith("CE") else "PE" if str(audit["trading_symbol"]).upper().endswith("PE") else ""
                wanted = "GAP UP" if option_type == "CE" and side == "BUY" else "GAP DOWN" if option_type == "PE" and side == "BUY" else ""
                forecast = self.database.cursor.execute(
                    """SELECT * FROM gap_probability_forecasts WHERE forecast_date=? AND target_date>? AND symbol=?
                       AND stage IN ('3:20 ACTIONABLE','3:40 CLOSE CONFIRMATION')
                       ORDER BY CASE stage WHEN '3:40 CLOSE CONFIRMATION' THEN 0 ELSE 1 END, generated_at DESC LIMIT 1""",
                    (now.date().isoformat(), now.date().isoformat(),
                     "BANKNIFTY" if "BANKNIFTY" in str(audit["trading_symbol"]).upper() else
                     "SENSEX" if "SENSEX" in str(audit["trading_symbol"]).upper() else "NIFTY"),
                ).fetchone()
                probability = float(forecast["gap_up_probability"] if wanted == "GAP UP" else forecast["gap_down_probability"]) if forecast and wanted else 0
                other = max(float(forecast["flat_probability"]), float(forecast["gap_down_probability"] if wanted == "GAP UP" else forecast["gap_up_probability"])) if forecast and wanted else 100
                try:
                    expiry_valid = datetime.fromisoformat(str(audit["expiry_date"] or "")[:10]).date() >= datetime.fromisoformat(str(forecast["target_date"])).date() if forecast else False
                except ValueError:
                    expiry_valid = False
                qualifies = (str(audit["product_type"]).upper() == "CARRYFORWARD" and expiry_valid and forecast
                             and str(forecast["predicted_class"]).upper() == wanted and probability >= 45
                             and probability - other >= 5 and int(forecast["confidence"]) >= 55
                             and int(forecast["data_quality"]) >= 70 and not settings.get("news_risk_pause", False))
                if qualifies:
                    self.database.update_execution_management(
                        audit_id, overnight_state="HELD", overnight_target_date=forecast["target_date"],
                        overnight_forecast_id=int(forecast["id"]), overnight_carry_price=price,
                        managed_state="OVERNIGHT_BROKER_POSITION_CONFIRMED",
                        message=f"REAL carry retained after broker-position reconciliation; {wanted} {probability:.1f}%.",
                    )
                    continue
            if not reason:
                self.database.update_execution_management(audit_id, status="REAL_OPEN", managed_state="REAL_OPEN_MANAGED")
                continue
            try:
                result = self.live_session.client.place_market_order({
                    "exchange": audit["exchange"], "symbol_token": audit["symbol_token"],
                    "trading_symbol": audit["trading_symbol"], "side": "SELL" if side == "BUY" else "BUY",
                    "quantity": expected, "product_type": audit["product_type"],
                })
                exit_id = str(result.get("order_id") or "")
                if not exit_id:
                    raise RuntimeError("Broker exit response did not include an order ID")
                self.database.update_execution_management(
                    audit_id, status="EXIT_SUBMITTED", managed_state="EXIT_FILL_PENDING", exit_order_id=exit_id,
                    message=f"{reason}; broker exit {exit_id} submitted. Fill not assumed.",
                )
                events.append({"audit_id": audit_id, "symbol": audit["trading_symbol"],
                               "outcome": f"REAL {reason} EXIT SUBMITTED", "ltp": price})
            except Exception as error:
                self.database.update_execution_management(
                    audit_id, status="EXIT_ATTENTION_REQUIRED", managed_state="EXIT_SUBMISSION_UNKNOWN",
                    message=f"{reason}; exit submission failed/unknown: {error}. Verify broker immediately.",
                )
        return events
