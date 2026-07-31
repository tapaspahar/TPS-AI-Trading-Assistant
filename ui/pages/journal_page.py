from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFormLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox
)

from core.database_manager import Database


class JournalPage(QWidget):

    def __init__(self):

        super().__init__()

        self.db = Database()

        layout = QVBoxLayout(self)

        title = QLabel("📒 Trade Journal")
        layout.addWidget(title)

        form = QFormLayout()

        self.dateInput = QLineEdit(datetime.now().strftime("%d-%m-%Y"))
        self.timeInput = QLineEdit(datetime.now().strftime("%H:%M:%S"))

        self.symbolInput = QLineEdit()
        self.strikeInput = QLineEdit()

        self.optionInput = QComboBox()
        self.optionInput.addItems(["CE", "PE"])

        self.entryInput = QLineEdit()
        self.exitInput = QLineEdit()
        self.quantityInput = QLineEdit()

        self.psychologyInput = QComboBox()
        self.psychologyInput.addItems([
            "Calm",
            "Confident",
            "Fear",
            "Greed",
            "FOMO",
            "Revenge"
        ])

        form.addRow("Date", self.dateInput)
        form.addRow("Time", self.timeInput)
        form.addRow("Symbol", self.symbolInput)
        form.addRow("Strike", self.strikeInput)
        form.addRow("Option", self.optionInput)
        form.addRow("Entry", self.entryInput)
        form.addRow("Exit", self.exitInput)
        form.addRow("Quantity", self.quantityInput)
        form.addRow("Psychology", self.psychologyInput)

        layout.addLayout(form)

        self.saveButton = QPushButton("💾 Save Trade")
        self.saveButton.clicked.connect(self.save_trade)

        layout.addWidget(self.saveButton)

        self.table = QTableWidget()
        layout.addWidget(self.table)

        self.load_trades()

    def save_trade(self):

        if self.symbolInput.text().strip() == "":
            QMessageBox.warning(self, "Warning", "Please enter Symbol.")
            return

        if self.strikeInput.text().strip() == "":
            QMessageBox.warning(self, "Warning", "Please enter Strike.")
            return

        if self.entryInput.text().strip() == "":
            QMessageBox.warning(self, "Warning", "Please enter Entry Price.")
            return

        if self.exitInput.text().strip() == "":
            QMessageBox.warning(self, "Warning", "Please enter Exit Price.")
            return

        if self.quantityInput.text().strip() == "":
            QMessageBox.warning(self, "Warning", "Please enter Quantity.")
            return

        try:

            self.db.save_trade(

                self.dateInput.text(),

                self.timeInput.text(),

                self.symbolInput.text().upper(),

                self.strikeInput.text(),

                self.optionInput.currentText(),

                float(self.entryInput.text()),

                float(self.exitInput.text()),

                int(self.quantityInput.text()),

                self.psychologyInput.currentText()

            )

            QMessageBox.information(
                self,
                "Success",
                "Trade Saved Successfully."
            )

            self.symbolInput.clear()
            self.strikeInput.clear()
            self.entryInput.clear()
            self.exitInput.clear()
            self.quantityInput.clear()

            self.dateInput.setText(
                datetime.now().strftime("%d-%m-%Y")
            )

            self.timeInput.setText(
                datetime.now().strftime("%H:%M:%S")
            )

            self.load_trades()

        except ValueError:

            QMessageBox.warning(
                self,
                "Invalid Input",
                "Entry, Exit and Quantity should be numeric."
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )

    def load_trades(self):

        data = self.db.get_all_trades()

        headers = [
            "Date",
            "Time",
            "Symbol",
            "Option",
            "Entry",
            "Exit",
            "Qty",
            "P&L",
            "Psychology"
        ]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data))

        for row, trade in enumerate(data):

            for col, value in enumerate(trade):

                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(str(value))
                )