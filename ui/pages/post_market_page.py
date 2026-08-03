from datetime import datetime

from PySide6.QtWidgets import QFormLayout, QLineEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.database_manager import Database


class PostMarketPage(QWidget):
    """Read-only timeline of snapshots captured while the application was running."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Post-Market Analysis — saved 5m / 15m candle and option-chain timeline"))
        form = QFormLayout()
        self.date_input = QLineEdit(datetime.now().strftime("%d-%m-%Y"))
        form.addRow("Trading date", self.date_input)
        layout.addLayout(form)
        button = QPushButton("Load Saved Market Report")
        button.clicked.connect(self.refresh)
        layout.addWidget(button)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Snapshot data is observational. Review it alongside the actual chart, broker execution and news before changing any strategy rule."))
        self.refresh()

    def refresh(self):
        snapshots = self.db.get_market_snapshots(self.date_input.text().strip())
        if not snapshots:
            self.summary.setText("No saved market snapshots for this date. Keep TPS running during market hours so it can record 5m / 15m data.")
            self.table.setRowCount(0)
            return
        by_timeframe = {timeframe: [row for row in snapshots if row["timeframe"] == timeframe] for timeframe in ("5m", "15m")}
        latest = snapshots[-1]
        oi_text = (
            f"Latest OI PCR: {float(latest['oi_pcr']):.2f} | Volume PCR: {float(latest['volume_pcr']):.2f} | "
            f"OI PCR change: {float(latest['oi_pcr_change'] or 0):+.4f} | Volume PCR change: {float(latest['volume_pcr_change'] or 0):+.4f}\n"
            f"Put-OI support: {latest['put_support'] or 'unavailable'} | Call-OI resistance: {latest['call_resistance'] or 'unavailable'}"
            if latest["oi_pcr"] is not None else
            "Latest option-chain OI/PCR was unavailable; candle snapshot was still saved."
        )
        self.summary.setText(
            f"Saved snapshots: {len(snapshots)} | 5m: {len(by_timeframe['5m'])} | 15m: {len(by_timeframe['15m'])}\n"
            f"Latest {latest['symbol']} close: {float(latest['close']):,.2f} | RSI 14: {float(latest['rsi_14'] or 0):.2f} | "
            f"ATR 14: {float(latest['atr_14'] or 0):.2f}\n{oi_text}"
        )
        headers = ["Captured", "Symbol", "TF", "Close", "Volume", "EMA 5", "EMA 20", "EMA 50", "VWAP", "SuperTrend", "RSI", "ATR", "OI PCR", "OI PCR Change", "Vol PCR", "Vol PCR Change", "Put Support", "Call Resistance"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(snapshots))
        for row, snapshot in enumerate(snapshots):
            values = (
                snapshot["captured_at"], snapshot["symbol"], snapshot["timeframe"], snapshot["close"], snapshot["volume"],
                snapshot["ema_5"], snapshot["ema_20"], snapshot["ema_50"], snapshot["vwap"], snapshot["supertrend"],
                snapshot["rsi_14"], snapshot["atr_14"], snapshot["oi_pcr"], snapshot["oi_pcr_change"], snapshot["volume_pcr"], snapshot["volume_pcr_change"],
                snapshot["put_support"], snapshot["call_resistance"],
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))
        self.table.resizeColumnsToContents()
