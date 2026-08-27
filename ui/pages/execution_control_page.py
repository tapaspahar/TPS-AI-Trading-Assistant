"""Explicit, session-locked broker execution console."""
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
        self.max_orders = QSpinBox(); self.max_orders.setRange(1, 20); self.max_orders.setValue(int(values.get("execution_max_orders_per_day", 3)))
        self.max_quantity = QSpinBox(); self.max_quantity.setRange(1, 10000); self.max_quantity.setValue(int(values.get("execution_max_quantity", 65)))
        self.max_value = QDoubleSpinBox(); self.max_value.setRange(1, 10_000_000); self.max_value.setDecimals(2); self.max_value.setValue(float(values.get("execution_max_order_value", 25000)))
        self.max_loss = QDoubleSpinBox(); self.max_loss.setRange(1, 10_000_000); self.max_loss.setDecimals(2); self.max_loss.setValue(float(values.get("execution_max_daily_loss", 1000)))
        save_limits = QPushButton("Save Execution Safety Limits"); save_limits.clicked.connect(self.save_limits)
        limits.addRow(self.enabled); limits.addRow("Maximum submitted orders/day", self.max_orders)
        limits.addRow("Maximum quantity/order", self.max_quantity); limits.addRow("Maximum order value (₹)", self.max_value)
        limits.addRow("Recorded realized-loss lock (₹)", self.max_loss); limits.addRow(save_limits)
        loss_note = QLabel("Yeh lock sirf TPS audit me available realized P&L par apply hota hai. Broker position/P&L sync ke bina ise complete account-level loss protection na samjhein.")
        loss_note.setWordWrap(True); limits.addRow(loss_note)
        layout.addWidget(limits_box)

        arm_box = QGroupBox("2. Unlock only for this app session")
        arm = QFormLayout(arm_box)
        self.arm_phrase = QLineEdit(); self.arm_phrase.setPlaceholderText(ExecutionService.UNLOCK_PHRASE)
        self.session_status = QLabel("LOCKED")
        arm_buttons = QHBoxLayout()
        arm_btn = QPushButton("Arm Session"); arm_btn.clicked.connect(self.arm_session)
        disarm_btn = QPushButton("Disarm"); disarm_btn.clicked.connect(self.disarm)
        kill_btn = QPushButton("EMERGENCY STOP"); kill_btn.clicked.connect(self.emergency_stop)
        arm_buttons.addWidget(arm_btn); arm_buttons.addWidget(disarm_btn); arm_buttons.addWidget(kill_btn)
        arm.addRow("Type ENABLE REAL TRADING", self.arm_phrase); arm.addRow("Session state", self.session_status); arm.addRow(arm_buttons)
        layout.addWidget(arm_box)

        order_box = QGroupBox("3. Stage one LIMIT order")
        form = QFormLayout(order_box)
        self.exchange = QComboBox(); self.exchange.addItems(("NFO", "BFO", "NSE", "BSE"))
        self.token = QLineEdit(); self.symbol = QLineEdit()
        self.side = QComboBox(); self.side.addItems(("BUY", "SELL"))
        self.quantity = QSpinBox(); self.quantity.setRange(1, 10000)
        self.price = QDoubleSpinBox(); self.price.setRange(0.05, 10_000_000); self.price.setDecimals(2)
        self.product = QComboBox(); self.product.addItems(("INTRADAY", "CARRYFORWARD"))
        self.final_phrase = QLineEdit(); self.final_phrase.setPlaceholderText("PLACE LIMIT ORDER")
        for label, widget in (("Exchange", self.exchange), ("Symbol token", self.token), ("Trading symbol", self.symbol),
                              ("Side", self.side), ("Quantity", self.quantity), ("Limit price", self.price),
                              ("Product", self.product), ("Final phrase", self.final_phrase)):
            form.addRow(label, widget)
        submit = QPushButton("Review & Submit Real LIMIT Order"); submit.clicked.connect(self.submit)
        refresh = QPushButton("Refresh Broker Order Status"); refresh.clicked.connect(self.refresh_status)
        form.addRow(submit); form.addRow(refresh)
        self.result = QLabel("No order submitted in this app session."); self.result.setWordWrap(True); form.addRow(self.result)
        layout.addWidget(order_box); layout.addStretch()

    def save_limits(self):
        values = self.store.load()
        values.update({
            "real_execution_enabled": self.enabled.isChecked(),
            "execution_max_orders_per_day": self.max_orders.value(),
            "execution_max_quantity": self.max_quantity.value(),
            "execution_max_order_value": self.max_value.value(),
            "execution_max_daily_loss": self.max_loss.value(),
        })
        self.store.save(values)
        self.service.disarm(); self.session_status.setText("LOCKED — safety settings saved")
        QMessageBox.information(self, "Safety settings", "Execution safety limits saved. Session remains LOCKED.")

    def arm_session(self):
        try:
            self.service.arm(self.arm_phrase.text())
            self.arm_phrase.clear(); self.session_status.setText("ARMED — this app session only")
        except Exception as error:
            QMessageBox.warning(self, "Execution remains locked", str(error))

    def disarm(self):
        self.service.disarm(); self.session_status.setText("LOCKED")

    def emergency_stop(self):
        self.service.emergency_stop(); self.session_status.setText("EMERGENCY STOP ACTIVE")
        QMessageBox.warning(self, "Emergency stop", "New submissions are blocked. Existing broker orders were not cancelled automatically; verify them in the broker order book.")

    def _order(self):
        return OrderRequest(self.exchange.currentText(), self.token.text().strip(), self.symbol.text().strip().upper(),
                            self.side.currentText(), self.quantity.value(), self.price.value(), self.product.currentText())

    def submit(self):
        order = self._order()
        review = (f"REAL LIMIT ORDER\n{order.side} {order.quantity} {order.trading_symbol} @ ₹{order.limit_price:.2f}\n"
                  f"Maximum notional: ₹{order.quantity * order.limit_price:,.2f}\n\nSubmit to Angel One?")
        if QMessageBox.question(self, "Final real-order review", review, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = self.service.submit(order, self.final_phrase.text())
            self.last_audit_id = result["audit_id"]
            self.service.disarm(); self.session_status.setText("LOCKED — re-arm required")
            self.final_phrase.clear()
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
