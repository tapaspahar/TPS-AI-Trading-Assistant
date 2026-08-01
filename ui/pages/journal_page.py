from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from models.trade import Trade


class JournalPage(QWidget):
    """A focused form for recording completed option trades."""

    def __init__(self):
        super().__init__()
        self.db = Database()
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

        self.save_button = QPushButton("Save Trade")
        self.save_button.clicked.connect(self.save_trade)
        layout.addWidget(self.save_button)
        self.table = QTableWidget()
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
        self.load_trades()

    def load_trades(self) -> None:
        headers = ["Date", "Time", "Symbol", "Option", "Entry", "Exit", "Qty", "P&L", "R:R", "Psychology", "AI", "Decision"]
        data = self.db.get_all_trades()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data))
        for row, trade in enumerate(data):
            for column, value in enumerate(trade):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
