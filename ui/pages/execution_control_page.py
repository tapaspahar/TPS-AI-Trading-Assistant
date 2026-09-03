"""Explicit, session-locked broker execution console."""
import json
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QDoubleSpinBox, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.settings_store import SettingsStore
from services.execution_service import ExecutionService, OrderRequest
from services.live_session import LiveSession


class ExecutionControlPage(QWidget):
    """Real orders require saved opt-in, session arm and per-order confirmation."""

    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        self.database = Database()
        self.service = ExecutionService(self.database, self.store, LiveSession)
        self.last_audit_id = None

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)

        title = QLabel("Safeguarded Broker Execution"); title.setObjectName("pageTitle"); layout.addWidget(title)
        warning = QLabel(
            "REAL MONEY AREA. Cutie kabhi signal, alert ya paper plan se automatic broker order nahi bhejegi. "
            "Har app launch par execution LOCKED rahega; sirf Angel One LIMIT order, market hours, caps, "
            "duplicate guard aur do explicit confirmations ke baad submit hoga. Broker acceptance fill confirmation nahi hai."
        )
        warning.setWordWrap(True); layout.addWidget(warning)

        limits_box = QGroupBox("1. Persistent safety limits (default execution OFF)")
        limits = QFormLayout(limits_box)
        values = self.store.load()
        self.enabled = QCheckBox("I understand this enables a real-money order console")
        self.enabled.setChecked(bool(values.get("real_execution_enabled", False)))
        self.pilot_enabled = QCheckBox("Enable Limited REAL Pilot Mode (session still requires activation)")
        self.pilot_enabled.setChecked(bool(values.get("limited_real_pilot_enabled", False)))
        self.managed_exits = QCheckBox("Monitor filled REAL positions and submit target/stop/time exits")
        self.managed_exits.setChecked(bool(values.get("real_managed_exit_enabled", True)))
        self.max_orders = QSpinBox(); self.max_orders.setRange(1, 20); self.max_orders.setValue(int(values.get("execution_max_orders_per_day", 3)))
        self.max_quantity = QSpinBox(); self.max_quantity.setRange(1, 10000); self.max_quantity.setValue(int(values.get("execution_max_quantity", 65)))
        self.max_value = QDoubleSpinBox(); self.max_value.setRange(1, 10_000_000); self.max_value.setDecimals(2); self.max_value.setValue(float(values.get("execution_max_order_value", 25000)))
        self.max_loss = QDoubleSpinBox(); self.max_loss.setRange(1, 10_000_000); self.max_loss.setDecimals(2); self.max_loss.setValue(float(values.get("execution_max_daily_loss", 1000)))
        save_limits = QPushButton("Save Execution Safety Limits"); save_limits.clicked.connect(self.save_limits)
        limits.addRow(self.enabled); limits.addRow(self.pilot_enabled); limits.addRow(self.managed_exits)
        limits.addRow("Maximum submitted orders/day", self.max_orders)
        limits.addRow("Maximum quantity/order", self.max_quantity); limits.addRow("Maximum order value (₹)", self.max_value)
        limits.addRow("Recorded realized-loss lock (₹)", self.max_loss); limits.addRow(save_limits)
        loss_note = QLabel(
            "Limited pilot code-level ceiling: maximum 2 accepted entries/day, quantity 65, per-trade planned risk 0.25% capital aur daily realized-loss 0.5% capital. "
            "Target + stop mandatory hain. UI me badi value likhne par bhi lower pilot ceiling apply hogi. "
            "Yeh lock sirf TPS audit me available realized P&L par apply hota hai; broker position/P&L sync ke bina ise complete account-level protection na samjhein."
        )
        loss_note.setWordWrap(True); limits.addRow(loss_note)
        layout.addWidget(limits_box)

        arm_box = QGroupBox("2. Unlock only for this app session")
        arm = QFormLayout(arm_box)
        self.arm_money_ack = QCheckBox("I understand ki REAL mode actual broker order place kar sakta hai")
        self.arm_session_ack = QCheckBox("Is app session ke liye REAL order execution activate karein")
        self.session_status = QLabel("LOCKED")
        arm_buttons = QHBoxLayout()
        arm_btn = QPushButton("Activate REAL Session"); arm_btn.clicked.connect(self.arm_session)
        one_click_btn = QPushButton("Start Today's One-Click REAL Pilot"); one_click_btn.clicked.connect(self.start_one_click_pilot)
        disarm_btn = QPushButton("Disarm"); disarm_btn.clicked.connect(self.disarm)
        kill_btn = QPushButton("EMERGENCY STOP"); kill_btn.clicked.connect(self.emergency_stop)
        arm_buttons.addWidget(arm_btn); arm_buttons.addWidget(one_click_btn); arm_buttons.addWidget(disarm_btn); arm_buttons.addWidget(kill_btn)
        arm.addRow(self.arm_money_ack); arm.addRow(self.arm_session_ack)
        arm.addRow("Session state", self.session_status); arm.addRow(arm_buttons)
        layout.addWidget(arm_box)

        order_box = QGroupBox("3. Stage one Paper or Real LIMIT order")
        form = QFormLayout(order_box)
        self.candidate_source = QLabel("No candidate transferred. Fields may be entered directly.")
        self.candidate_source.setWordWrap(True)
        self.leg_selector = QComboBox()
        self.leg_selector.currentIndexChanged.connect(self._load_selected_leg)
        self._candidate_legs = []
        self.exchange = QComboBox(); self.exchange.addItems(("NFO", "BFO", "NSE", "BSE"))
        self.token = QLineEdit(); self.symbol = QLineEdit()
        self.expiry = QLineEdit(); self.expiry.setPlaceholderText("YYYY-MM-DD; required for overnight options")
        self.side = QComboBox(); self.side.addItems(("BUY", "SELL"))
        self.quantity = QSpinBox(); self.quantity.setRange(1, 10000)
        self.price = QDoubleSpinBox(); self.price.setRange(0.05, 10_000_000); self.price.setDecimals(2)
        self.product = QComboBox(); self.product.addItems(("INTRADAY", "CARRYFORWARD"))
        self.target_basis = QComboBox(); self.stop_basis = QComboBox()
        for widget in (self.target_basis, self.stop_basis):
            widget.addItem("Exact exit price", "PRICE"); widget.addItem("₹ move from entry", "AMOUNT"); widget.addItem("% move from entry", "PERCENT")
        self.target_basis.setCurrentIndex(max(0, self.target_basis.findData(values.get("execution_target_basis", "PERCENT"))))
        self.stop_basis.setCurrentIndex(max(0, self.stop_basis.findData(values.get("execution_stop_basis", "PERCENT"))))
        self.target_value = QDoubleSpinBox(); self.target_value.setRange(0.01, 10_000_000); self.target_value.setDecimals(2); self.target_value.setValue(float(values.get("execution_target_value", 20)))
        self.stop_value = QDoubleSpinBox(); self.stop_value.setRange(0.01, 10_000_000); self.stop_value.setDecimals(2); self.stop_value.setValue(float(values.get("execution_stop_value", 10)))
        self.time_exit_enabled = QCheckBox("Use planned time exit"); self.time_exit_enabled.setChecked(bool(values.get("execution_time_exit_enabled", True)))
        self.time_exit = QLineEdit(str(values.get("execution_time_exit", "15:20"))); self.time_exit.setPlaceholderText("HH:MM")
        self.plan_preview = QLabel("Enter an entry price, then calculate exact target and stop levels."); self.plan_preview.setWordWrap(True)
        calculate = QPushButton("Calculate Entry / Target / Stop / Exit Plan"); calculate.clicked.connect(self.calculate_plan)
        self.final_order_ack = QCheckBox("I have reviewed entry, target, stop, quantity and REAL order details")
        form.addRow("Transferred candidate", self.candidate_source)
        form.addRow("Strategy leg", self.leg_selector)
        for label, widget in (("Exchange", self.exchange), ("Symbol token", self.token), ("Trading symbol", self.symbol),
                              ("Expiry", self.expiry),
                              ("Side", self.side), ("Quantity", self.quantity), ("Limit price", self.price),
                              ("Product", self.product), ("Target type", self.target_basis), ("Target value", self.target_value),
                              ("Stop type", self.stop_basis), ("Stop value", self.stop_value), ("Time exit", self.time_exit)):
            form.addRow(label, widget)
        form.addRow(self.time_exit_enabled); form.addRow(calculate); form.addRow(self.plan_preview)
        form.addRow(self.final_order_ack)
        self.submit_button = QPushButton(); self.submit_button.clicked.connect(self.submit)
        self._refresh_mode_label()
        refresh = QPushButton("Refresh Broker Order Status"); refresh.clicked.connect(self.refresh_status)
        form.addRow(self.submit_button); form.addRow(refresh)
        self.result = QLabel("No order submitted in this app session."); self.result.setWordWrap(True); form.addRow(self.result)
        layout.addWidget(order_box); layout.addStretch()

    def save_limits(self):
        values = self.store.load()
        values.update({
            "real_execution_enabled": self.enabled.isChecked(),
            "limited_real_pilot_enabled": self.pilot_enabled.isChecked(),
            "real_managed_exit_enabled": self.managed_exits.isChecked(),
            "execution_max_orders_per_day": self.max_orders.value(),
            "execution_max_quantity": self.max_quantity.value(),
            "execution_max_order_value": self.max_value.value(),
            "execution_max_daily_loss": self.max_loss.value(),
        })
        self.store.save(values)
        self.service.disarm(); self.session_status.setText("LOCKED — safety settings saved")
        QMessageBox.information(self, "Safety settings", "Execution safety limits saved. Session remains LOCKED.")

    def arm_session(self):
        if not self.arm_money_ack.isChecked() or not self.arm_session_ack.isChecked():
            QMessageBox.warning(self, "Execution remains locked", "REAL session activate karne ke liye dono safety ticks select karein.")
            return
        answer = QMessageBox.question(
            self, "Activate REAL execution",
            "REAL execution is app session ke liye activate hogi aur actual broker orders place kar sakti hai. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.service.arm(ExecutionService.UNLOCK_PHRASE)
            self.session_status.setText("ARMED — this app session only")
        except Exception as error:
            QMessageBox.warning(self, "Execution remains locked", str(error))

    def start_one_click_pilot(self, command=None):
        """One action is the daily consent; later eligible orders use automatic preflight."""
        values = self.store.load()
        values.update({"execution_mode": "REAL", "real_execution_enabled": True,
                       "limited_real_pilot_enabled": True})
        if command:
            values["real_pilot_max_orders"] = min(2, int(command.get("max_trades", 2)))
            values["execution_max_daily_loss"] = float(command.get("max_loss", values["execution_max_daily_loss"]))
            values["execution_max_quantity"] = min(65, int(command.get("lots", 1)) * 65)
        self.store.save(values)
        self.enabled.setChecked(True); self.pilot_enabled.setChecked(True)
        try:
            self.service.arm(ExecutionService.UNLOCK_PHRASE)
        except Exception as error:
            self.session_status.setText(f"PILOT NOT STARTED — {error}")
            return False
        self.session_status.setText("ONE-CLICK REAL PILOT ARMED — automatic preflight active")
        self.arm_money_ack.setChecked(True); self.arm_session_ack.setChecked(True)
        return True

    def disarm(self):
        self.service.disarm(); self.session_status.setText("LOCKED")
        self.arm_money_ack.setChecked(False); self.arm_session_ack.setChecked(False)
        self.final_order_ack.setChecked(False)

    def emergency_stop(self):
        self.service.emergency_stop(); self.session_status.setText("EMERGENCY STOP ACTIVE")
        self.arm_money_ack.setChecked(False); self.arm_session_ack.setChecked(False)
        self.final_order_ack.setChecked(False)
        QMessageBox.warning(self, "Emergency stop", "New submissions are blocked. Existing broker orders were not cancelled automatically; verify them in the broker order book.")

    def _order(self):
        target = ExecutionService.exit_price(self.price.value(), self.side.currentText(), self.target_basis.currentData(), self.target_value.value(), "TARGET")
        stop = ExecutionService.exit_price(self.price.value(), self.side.currentText(), self.stop_basis.currentData(), self.stop_value.value(), "STOP")
        return OrderRequest(self.exchange.currentText(), self.token.text().strip(), self.symbol.text().strip().upper(),
                            self.side.currentText(), self.quantity.value(), self.price.value(), self.product.currentText(),
                            target, stop, self.time_exit.text().strip() if self.time_exit_enabled.isChecked() else "",
                            expiry_date=self.expiry.text().strip())

    def _refresh_mode_label(self):
        mode = str(self.store.load().get("execution_mode", "PAPER")).upper()
        self.submit_button.setText("Save Paper Order Plan (no broker order)" if mode == "PAPER" else "Review & Submit Real LIMIT Order")

    def refresh_mode(self):
        self._refresh_mode_label()

    def load_candidate(self, payload: dict):
        """Transfer a research candidate into review without bypassing execution safeguards."""
        kind = str(payload.get("kind") or "").upper()
        record = dict(payload.get("record") or {})
        legs = []
        if kind == "STRATEGY":
            try:
                raw_legs = json.loads(record.get("legs_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                raw_legs = []
            underlying = str(record.get("symbol") or "").upper()
            for index, leg in enumerate(raw_legs, 1):
                legs.append(self._normalise_leg(leg, underlying, f"Leg {index}"))
            title = record.get("friendly_name") or record.get("strategy_name") or "Defined-risk strategy"
            self.candidate_source.setText(
                f"Strategy: {title}. {len(legs)} legs transferred. Each leg must be reviewed and submitted separately; "
                "this is not atomic basket execution, so partial-fill and margin risk remain."
            )
        else:
            try:
                details = json.loads(record.get("details_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                details = {}
            action = str(record.get("action") or "BUY").upper()
            legs = [self._normalise_leg({
                "action": "SELL" if action.startswith("SELL") else "BUY",
                "contract": record.get("instrument") or record.get("symbol"),
                "price": record.get("entry"), "quantity": record.get("quantity") or 1,
                "token": details.get("symbol_token") or details.get("token"),
                "exchange": details.get("exchange"),
                "target": record.get("target_1"), "stop": record.get("stop"),
            }, str(record.get("symbol") or ""), "Opportunity")]
            self.candidate_source.setText(
                f"Opportunity Radar: {record.get('action')} {record.get('instrument') or record.get('symbol')}. "
                "Transferred for safeguarded review; no order has been sent."
            )
        self._candidate_legs = legs
        missing_tokens = sum(not leg["token"] for leg in legs)
        if missing_tokens:
            self.candidate_source.setText(
                self.candidate_source.text()
                + f" {missing_tokens} leg(s) ka broker token unresolved hai; REAL submit token milne tak blocked rahega."
            )
        self.leg_selector.blockSignals(True); self.leg_selector.clear()
        for leg in legs:
            self.leg_selector.addItem(f"{leg['label']} — {leg['side']} {leg['symbol']}")
        self.leg_selector.blockSignals(False)
        if legs:
            self.leg_selector.setCurrentIndex(0); self._load_selected_leg(0)
        self.final_order_ack.setChecked(False)
        self._refresh_mode_label()

    @staticmethod
    def _normalise_leg(leg, underlying, label):
        symbol = str(leg.get("trading_symbol") or leg.get("tradingsymbol") or leg.get("contract") or leg.get("symbol") or "").upper()
        exchange = str(leg.get("exchange") or ("BFO" if underlying == "SENSEX" else "NFO" if not symbol.endswith("-EQ") else "NSE")).upper()
        return {
            "label": label, "exchange": exchange,
            "token": str(leg.get("symbol_token") or leg.get("symboltoken") or leg.get("token") or ""),
            "symbol": symbol, "side": str(leg.get("action") or leg.get("side") or "BUY").upper(),
            "quantity": max(1, int(float(leg.get("quantity") or 1))),
            "price": float(leg.get("price") or leg.get("entry") or 0),
            "target": float(leg.get("target") or 0), "stop": float(leg.get("stop") or 0),
            "expiry": str(leg.get("expiry") or leg.get("expiry_date") or ""),
        }

    def _load_selected_leg(self, index):
        if index < 0 or index >= len(self._candidate_legs):
            return
        leg = self._candidate_legs[index]
        self.exchange.setCurrentIndex(max(0, self.exchange.findText(leg["exchange"])))
        self.token.setText(leg["token"]); self.symbol.setText(leg["symbol"])
        self.side.setCurrentIndex(max(0, self.side.findText(leg["side"])))
        self.quantity.setValue(leg["quantity"])
        if leg["price"] > 0: self.price.setValue(leg["price"])
        if leg["target"] > 0:
            self.target_basis.setCurrentIndex(self.target_basis.findData("PRICE")); self.target_value.setValue(leg["target"])
        if leg["stop"] > 0:
            self.stop_basis.setCurrentIndex(self.stop_basis.findData("PRICE")); self.stop_value.setValue(leg["stop"])
        self.expiry.setText(str(leg.get("expiry") or ""))
        self.calculate_plan()

    def calculate_plan(self):
        try:
            order = self._order()
            self.plan_preview.setText(
                f"Entry ₹{order.limit_price:.2f} | Target ₹{order.target_price:.2f} | Stop ₹{order.stop_price:.2f}"
                + (f" | Time exit {order.time_exit}" if order.time_exit else " | No time exit")
                + f" | Quantity {order.quantity} | Entry value ₹{order.quantity * order.limit_price:,.2f}"
            )
        except Exception as error:
            self.plan_preview.setText(f"Plan invalid: {error}")

    def submit(self):
        try:
            order = self._order()
        except Exception as error:
            QMessageBox.warning(self, "Invalid exit plan", str(error)); return
        mode = str(self.store.load().get("execution_mode", "PAPER")).upper()
        if mode == "PAPER":
            try:
                result = self.service.stage_paper(order)
                self.last_audit_id = None
                self.result.setText(
                    f"Paper plan saved — {order.side} {order.quantity} {order.trading_symbol} @ ₹{order.limit_price:.2f} | "
                    f"Target ₹{order.target_price:.2f} | Stop ₹{order.stop_price:.2f}"
                    + (f" | Time exit {order.time_exit}" if order.time_exit else "")
                    + ". No broker order was placed."
                )
                QMessageBox.information(self, "Paper plan saved", "Plan audit me save ho gaya. Broker ko koi order nahi bheja gaya.")
            except Exception as error:
                QMessageBox.warning(self, "Paper plan not saved", str(error))
            return
        if not self.final_order_ack.isChecked():
            QMessageBox.warning(self, "Final review required", "REAL order submit karne se pehle final order-review tick select karein.")
            return
        review = (f"REAL LIMIT ORDER\n{order.side} {order.quantity} {order.trading_symbol} @ ₹{order.limit_price:.2f}\n"
                  f"Planned target ₹{order.target_price:.2f} | planned stop ₹{order.stop_price:.2f}"
                  + (f" | time exit {order.time_exit}" if order.time_exit else "")
                  + f"\nMaximum entry value: ₹{order.quantity * order.limit_price:,.2f}\n\n"
                    "Entry fill ke baad enabled managed lifecycle broker position reconcile karke target/stop/time exit submit karega. "
                    "App/broker connection band hone par app-managed exit kaam nahi kar sakta. Submit to Angel One?")
        if QMessageBox.question(self, "Final real-order review", review, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = self.service.submit(order, "PLACE LIMIT ORDER")
            self.last_audit_id = result["audit_id"]
            self.service.disarm(); self.session_status.setText("LOCKED — re-arm required")
            self.final_order_ack.setChecked(False)
            self.arm_money_ack.setChecked(False); self.arm_session_ack.setChecked(False)
            self.result.setText(f"Broker accepted order ID {result.get('order_id') or 'pending'}. Status: ACCEPTED_NOT_FILLED. Refresh status before assuming execution.")
        except Exception as error:
            self.result.setText(f"Order not submitted: {error}")
            QMessageBox.warning(
                self, "Order blocked or status uncertain",
                f"{error}\n\nAgar request broker tak pahunchne ki possibility ho, broker order book verify kiye bina retry na karein.",
            )

    def refresh_status(self):
        if not self.last_audit_id:
            QMessageBox.information(self, "Order status", "No order was submitted in this app session."); return
        try:
            row = self.service.refresh_status(self.last_audit_id)
            self.result.setText(f"Latest broker status: {row.get('status') or row.get('orderstatus') or 'UNKNOWN'} | Order ID: {row.get('orderid') or row.get('orderId')}")
        except Exception as error:
            QMessageBox.warning(self, "Status unavailable", str(error))
