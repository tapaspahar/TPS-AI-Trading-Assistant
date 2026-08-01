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
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Trade Journal"))

        form = QFormLayout()
        self.date_input = QLineEdit(datetime.now().strftime("%d-%m-%Y"))
        self.time_input = QLineEdit(datetime.now().strftime("%H:%M"))
        self.symbol_input = QLineEdit()
        self.strike_input = QLineEdit()
        self.option_input = QComboBox(); self.option_input.addItems(["CE", "PE"])
        self.entry_input, self.exit_input = QLineEdit(), QLineEdit()
        self.stoploss_input, self.target_input = QLineEdit(), QLineEdit()
        self.quantity_input = QLineEdit()
        self.psychology_input = QComboBox()
        self.psychology_input.addItems(["Calm", "Confident", "Fear", "Greed", "FOMO", "Revenge"])
        for label, widget in (
            ("Date", self.date_input), ("Time", self.time_input), ("Symbol", self.symbol_input),
            ("Strike", self.strike_input), ("Option", self.option_input), ("Entry", self.entry_input),
            ("Exit", self.exit_input), ("Stop loss", self.stoploss_input), ("Target", self.target_input),
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

        self.save_button = QPushButton("Save Trade")
        self.save_button.clicked.connect(self.save_trade)
        layout.addWidget(self.save_button)
        self.delete_button = QPushButton("Delete Selected Trade")
        self.delete_button.clicked.connect(self.delete_selected_trade)
        layout.addWidget(self.delete_button)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self.load_trades()

    def _build_trade(self) -> Trade:
        return Trade(
            trade_date=self.date_input.text().strip(), trade_time=self.time_input.text().strip(),
            market="OPTIONS", symbol=self.symbol_input.text().strip(), expiry="",
            strike=self.strike_input.text().strip(), option=self.option_input.currentText(),
            entry=float(self.entry_input.text()), exit=float(self.exit_input.text()),
            stoploss=float(self.stoploss_input.text()), target=float(self.target_input.text()),
            quantity=int(self.quantity_input.text()), psychology_before=self.psychology_input.currentText(),
            trend=self.trend_check.isChecked(), vwap=self.vwap_check.isChecked(),
            ema=self.ema_check.isChecked(), volume=self.volume_check.isChecked(), oi=self.oi_check.isChecked(),
        )

    def save_trade(self) -> None:
        try:
            self.db.save_trade(self._build_trade())
        except ValueError as error:
            QMessageBox.warning(self, "Invalid trade", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Could not save trade", str(error))
            return

        QMessageBox.information(self, "Saved", "Trade saved successfully.")
        for field in (self.symbol_input, self.strike_input, self.entry_input, self.exit_input,
                      self.stoploss_input, self.target_input, self.quantity_input):
            field.clear()
        for checkbox in (self.trend_check, self.vwap_check, self.ema_check, self.volume_check, self.oi_check):
            checkbox.setChecked(False)
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

    def load_trades(self) -> None:
        headers = ["ID", "Date", "Time", "Symbol", "Option", "Entry", "Exit", "Qty", "P&L", "R:R", "Psychology", "AI", "Decision"]
        data = self.db.get_journal_rows()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data))
        for row, trade in enumerate(data):
            for column, value in enumerate(trade):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

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
