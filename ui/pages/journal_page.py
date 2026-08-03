from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Signal

from core.database_manager import Database
from models.trade import Trade
from core.settings_store import SettingsStore


class JournalPage(QWidget):
    """A focused form for recording completed option trades."""
    trade_saved = Signal()

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings_store = SettingsStore()
        self.current_rule_version = "Manual / unclassified"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Trade Journal"))
        self.plan_summary = QLabel("No review plan loaded. Quantity can be entered manually for completed trades.")
        self.plan_summary.setWordWrap(True)
        layout.addWidget(self.plan_summary)

        form = QFormLayout()
        self.date_input = QLineEdit(datetime.now().strftime("%d-%m-%Y"))
        self.time_input = QLineEdit(datetime.now().strftime("%H:%M"))
        self.symbol_input = QLineEdit()
        self.strike_input = QLineEdit()
        self.option_input = QComboBox(); self.option_input.addItems(["CE", "PE"])
        self.entry_input, self.exit_input = QLineEdit(), QLineEdit()
        self.outcome_input = QComboBox(); self.outcome_input.addItems(["Manual Exit", "Target Hit", "Stop Loss Hit"])
        self.stoploss_input, self.target_input = QLineEdit(), QLineEdit()
        self.quantity_input = QLineEdit()
        self.psychology_input = QComboBox()
        self.psychology_input.addItems(["Calm", "Confident", "Fear", "Greed", "FOMO", "Revenge"])
        for label, widget in (
            ("Date", self.date_input), ("Time", self.time_input), ("Symbol", self.symbol_input),
            ("Strike", self.strike_input), ("Option", self.option_input), ("Entry", self.entry_input),
            ("Exit", self.exit_input), ("Exit outcome", self.outcome_input), ("Stop loss", self.stoploss_input), ("Target", self.target_input),
            ("Quantity", self.quantity_input), ("Psychology", self.psychology_input),
        ):
            form.addRow(label, widget)
        layout.addLayout(form)

        confirmations = QGroupBox("Technical confirmations")
        confirmation_layout = QHBoxLayout(confirmations)
        self.trend_check = QCheckBox("Trend")
        self.vwap_check = QCheckBox("VWAP")
        self.ema_check = QCheckBox("EMA")
        self.volume_check = QCheckBox("Volume")
        self.oi_check = QCheckBox("OI")
        for checkbox in (self.trend_check, self.vwap_check, self.ema_check, self.volume_check, self.oi_check):
            confirmation_layout.addWidget(checkbox)
        confirmation_layout.addStretch()
        layout.addWidget(confirmations)

        self.save_button = QPushButton("Save Open Trade")
        self.save_button.clicked.connect(self.save_open_trade)
        layout.addWidget(self.save_button)
        self.close_button = QPushButton("Close Selected Trade (Save Actual Exit)")
        self.close_button.clicked.connect(self.close_selected_trade)
        layout.addWidget(self.close_button)
        self.delete_button = QPushButton("Delete Selected Trade")
        self.delete_button.clicked.connect(self.delete_selected_trade)
        layout.addWidget(self.delete_button)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.load_selected_trade)
        layout.addWidget(self.table)
        self.load_trades()

    def _build_trade(self, require_exit: bool = False) -> Trade:
        exit_text = self.exit_input.text().strip()
        if require_exit and not exit_text:
            raise ValueError("Enter the actual exit price after the trade is closed.")
        return Trade(
            trade_date=self.date_input.text().strip(), trade_time=self.time_input.text().strip(),
            market="OPTIONS", symbol=self.symbol_input.text().strip(), expiry="",
            strike=self.strike_input.text().strip(), option=self.option_input.currentText(),
            entry=float(self.entry_input.text()), exit=float(exit_text) if exit_text else 0.0,
            stoploss=float(self.stoploss_input.text()), target=float(self.target_input.text()),
            quantity=int(self.quantity_input.text()), psychology_before=self.psychology_input.currentText(), setup=self.current_rule_version,
            trend=self.trend_check.isChecked(), vwap=self.vwap_check.isChecked(),
            ema=self.ema_check.isChecked(), volume=self.volume_check.isChecked(), oi=self.oi_check.isChecked(),
        )

    def save_open_trade(self) -> None:
        try:
            self.db.save_open_trade(self._build_trade())
        except ValueError as error:
            QMessageBox.warning(self, "Invalid trade", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Could not save trade", str(error))
            return

        QMessageBox.information(self, "Open trade saved", "Open trade saved. Select its row later, enter the actual exit price, then use Close Selected Trade.")
        for field in (self.symbol_input, self.strike_input, self.entry_input, self.exit_input,
                      self.stoploss_input, self.target_input, self.quantity_input):
            field.clear()
        for checkbox in (self.trend_check, self.vwap_check, self.ema_check, self.volume_check, self.oi_check):
            checkbox.setChecked(False)
        self.load_trades()
        self.trade_saved.emit()
        self._show_daily_guardrail()

    def close_selected_trade(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select an open trade", "Select the open trade row, enter its actual exit price, then close it.")
            return
        try:
            exit_price = float(self.exit_input.text().strip())
            trade_id = int(self.table.item(row, 0).text())
            if not self.db.close_trade(trade_id, exit_price, self.outcome_input.currentText()):
                QMessageBox.warning(self, "Trade not found", "The selected trade no longer exists. Refreshing the table.")
                self.load_trades()
                return
        except ValueError as error:
            QMessageBox.warning(self, "Invalid exit", str(error))
            return
        QMessageBox.information(self, "Trade closed", "Actual exit and outcome saved. P&L and R:R have been calculated for this trade.")
        self.load_trades()
        self.trade_saved.emit()
        self._show_daily_guardrail()

    def _show_daily_guardrail(self) -> None:
        """Warn after recording, without preventing journal history from being saved."""
        settings = self.settings_store.load()
        summary = self.db.get_day_summary(self.date_input.text().strip())
        loss_limit = settings["capital"] * settings["daily_loss_percent"] / 100
        if summary["trades"] > settings["max_trades_per_day"]:
            QMessageBox.warning(self, "Trade limit warning", "Today's recorded trades exceed your configured daily limit.")
        elif summary["pnl"] <= -loss_limit:
            QMessageBox.warning(self, "Daily loss warning", "Today's recorded loss exceeds your configured daily-loss limit.")

    def set_symbol_from_capture(self, symbol: str) -> None:
        self.symbol_input.setText(symbol)

    def load_trade_plan(self, plan: dict) -> None:
        """Pre-fill a review draft; it remains unsaved until actual execution is recorded."""
        contract = plan["contract"]
        self.date_input.setText(datetime.now().strftime("%d-%m-%Y"))
        self.time_input.setText(datetime.now().strftime("%H:%M"))
        self.symbol_input.setText(plan["underlying"])
        self.strike_input.setText(f"{float(contract['strike']):.0f}")
        self.option_input.setCurrentText(plan["option_type"])
        self.outcome_input.setCurrentText("Manual Exit")
        self.entry_input.setText(f"{plan['entry']:.2f}")
        self.exit_input.clear()
        self.stoploss_input.setText(f"{plan['stoploss']:.2f}")
        self.target_input.setText(f"{plan['target']:.2f}")
        self.quantity_input.setText(str(plan["quantity"]))
        self.plan_summary.setText(
            f"Review plan quantity: {plan['lots']} lot(s) × {plan['lot_size']} = {plan['quantity']} quantity. "
            f"Estimated premium risk: ₹{plan['estimated_risk']:,.2f} (configured cap: ₹{plan['risk_cap']:,.2f})."
        )
        self.current_rule_version = plan.get("rule_version", "TPS V2 strict")
        for checkbox in (self.trend_check, self.vwap_check, self.ema_check, self.volume_check, self.oi_check):
            checkbox.setChecked(True)
        QMessageBox.information(
            self, "Review trade plan",
            "Draft pre-filled. TPS did not place or save an order. Verify the live Angel One premium and enter the actual exit later before saving the journal entry.",
        )

    def load_trades(self) -> None:
        headers = ["ID", "Date", "Time", "Symbol", "Strike", "Option", "Entry", "Stop Loss", "Target", "Exit", "Status", "Outcome", "Qty", "P&L", "R:R", "Psychology", "AI", "Decision"]
        data = self.db.get_journal_rows()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data))
        for row, trade in enumerate(data):
            for column, value in enumerate(trade):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def load_selected_trade(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        trade = self.db.get_trade(int(item.text()))
        if not trade:
            return
        self.date_input.setText(trade["trade_date"])
        self.time_input.setText(trade["trade_time"])
        self.symbol_input.setText(trade["symbol"])
        self.strike_input.setText(trade["strike"] or "")
        self.option_input.setCurrentText(trade["option_type"] or "CE")
        self.entry_input.setText(f"{float(trade['entry']):.2f}")
        self.stoploss_input.setText(f"{float(trade['stoploss']):.2f}")
        self.target_input.setText(f"{float(trade['target']):.2f}")
        self.quantity_input.setText(str(trade["quantity"]))
        if trade["status"] == "OPEN":
            self.exit_input.clear()
            self.outcome_input.setCurrentText("Manual Exit")
            self.plan_summary.setText("Selected OPEN trade: enter the actual exit price above, then click Close Selected Trade.")
        else:
            self.exit_input.setText(f"{float(trade['exit']):.2f}")
            self.outcome_input.setCurrentText(str(trade["outcome"]).title())
            self.plan_summary.setText("Selected CLOSED trade: exit, P&L and R:R have already been recorded.")

    def delete_selected_trade(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a trade", "Select one table row before deleting it.")
            return
        trade_id = int(self.table.item(row, 0).text())
        answer = QMessageBox.question(self, "Delete trade", "Delete the selected trade permanently?")
        if answer != QMessageBox.Yes:
            return
        if self.db.delete_trade(trade_id):
            self.load_trades()
            self.trade_saved.emit()
        else:
            QMessageBox.warning(self, "Trade not found", "This trade has already been removed. Refreshing the table.")
            self.load_trades()
