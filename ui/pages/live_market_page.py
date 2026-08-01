from datetime import datetime

from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class LiveMarketPage(QWidget):
    """Demonstration snapshot until a licensed market-data provider is connected."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Market Snapshot (simulation — not live market data)"))
        self.updated = QLabel()
        layout.addWidget(self.updated)
        self.table = QTableWidget(3, 4)
        self.table.setHorizontalHeaderLabels(["Index", "Reference", "Change", "Status"])
        layout.addWidget(self.table)
        refresh = QPushButton("Refresh Sample Snapshot")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addWidget(QLabel("Connect an approved broker or data-provider API before using market prices for trading decisions."))
        self.refresh()

    def refresh(self):
        rows = [("NIFTY 50", "24,850.00", "+0.35%", "Sample"),
                ("BANK NIFTY", "55,200.00", "+0.20%", "Sample"),
                ("INDIA VIX", "13.20", "-1.10%", "Sample")]
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.updated.setText(f"Sample refreshed: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
