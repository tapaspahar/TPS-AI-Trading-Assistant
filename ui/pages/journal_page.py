from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database


class JournalPage(QWidget):
    """Read-only journal populated exclusively by automatic TPS workflows."""

    trade_saved = Signal()
    open_backtesting = Signal()

    def __init__(self):
        super().__init__()
        self.db = Database()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 18)
        layout.setSpacing(10)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        title = QLabel("Automatic Trade Journal")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel(
            "Cutie automatically records every captured paper trade, monitored exit, target, "
            "stop-loss, time-exit, P&L and decision evidence. Manual entry or manual outcome "
            "editing is disabled so validation accuracy remains trustworthy."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Automatic Journal")
        self.refresh_button.clicked.connect(self.load_trades)
        self.review_button = QPushButton("Review Selected Stop-Loss Evidence")
        self.review_button.clicked.connect(self.review_stoploss_hit)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.review_button)
        layout.addLayout(actions)

        self.summary = QLabel("Loading automatic trade records...")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.load_selected_trade)
        self.table.setMinimumHeight(430)
        layout.addWidget(self.table)

        self.selected_details = QLabel("Select a row to view its automatic result and evidence summary.")
        self.selected_details.setWordWrap(True)
        self.selected_details.setMinimumHeight(80)
        layout.addWidget(self.selected_details)
        self.load_trades()

    def load_trades(self) -> None:
        headers = [
            "Trade", "ID", "Date", "Time", "Symbol", "Strike", "Option", "Entry",
            "Stop Loss", "Target", "Exit", "Status", "Outcome", "Qty", "P&L", "R:R",
            "Psychology", "AI", "Decision",
        ]
        data = self.db.get_journal_rows()
        self.table.blockSignals(True)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data))
        for row, trade in enumerate(data):
            marker = QTableWidgetItem("Select")
            marker.setTextAlignment(0x0084)
            self.table.setItem(row, 0, marker)
            for column, value in enumerate(trade, start=1):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 92)
        self.table.blockSignals(False)
        closed = sum(1 for row in data if str(row[10]).upper() == "CLOSED")
        self.summary.setText(
            f"Automatic records: {len(data)} | Closed: {closed} | Open/monitoring: {len(data) - closed}. "
            "New records and exits are written by the auto-paper engine only."
        )

    def load_selected_trade(self) -> None:
        row = self.table.currentRow()
        for index in range(self.table.rowCount()):
            marker = self.table.item(index, 0)
            if marker:
                marker.setText("✓ Selected" if index == row else "Select")
        if row < 0 or not self.table.item(row, 1):
            return
        trade = self.db.get_trade(int(self.table.item(row, 1).text()))
        if not trade:
            return
        self.selected_details.setText(
            f"{trade['symbol']} {trade['strike'] or ''} {trade['option_type'] or ''} | "
            f"Status: {trade['status']} | Outcome: {trade['outcome'] or 'Monitoring'} | "
            f"Entry ₹{float(trade['entry']):.2f} | Stop ₹{float(trade['stoploss']):.2f} | "
            f"Target ₹{float(trade['target']):.2f} | P&L ₹{float(trade['pnl'] or 0):,.2f} | "
            f"AI decision: {trade['ai_decision'] or '-'}"
        )

    def review_stoploss_hit(self) -> None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 1):
            self.selected_details.setText("Stop-loss evidence review ke liye ek closed Stop Loss Hit row select karein.")
            return
        trade = self.db.get_trade(int(self.table.item(row, 1).text()))
        if not trade or trade["outcome"] != "STOP LOSS HIT":
            self.selected_details.setText("Selected record Stop Loss Hit nahi hai.")
            return
        snapshots = [
            snapshot for snapshot in self.db.get_market_snapshots(trade["trade_date"])
            if snapshot["symbol"] == trade["symbol"]
        ]
        timeframes = ", ".join(sorted({snapshot["timeframe"] for snapshot in snapshots})) or "none"
        self.selected_details.setText(
            f"Cutie review: {trade['symbol']} {trade['strike'] or ''} {trade['option_type']} ke liye "
            f"{len(snapshots)} same-day snapshot(s) ({timeframes}) saved hain. "
            f"Confirmations: trend={bool(trade['trend'])}, VWAP={bool(trade['vwap'])}, "
            f"EMA={bool(trade['ema'])}, volume={bool(trade['volume'])}, OI={bool(trade['oi'])}. "
            "Historical replay khola ja raha hai; ek result ke basis par risk increase na karein."
        )
        self.open_backtesting.emit()

    def set_symbol_from_capture(self, _symbol: str) -> None:
        return

    def load_trade_plan(self, _plan: dict) -> None:
        self.load_trades()
