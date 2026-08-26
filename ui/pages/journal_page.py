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
        actions.addWidget(self.refresh_button)
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

        strategy_title = QLabel("Automatic Defined-Risk Strategy Trades")
        strategy_title.setObjectName("sectionTitle")
        layout.addWidget(strategy_title)
        strategy_note = QLabel(
            "Cutie ke multi-leg paper strategies yahan friendly name, payoff risk reserve, predefined maximum benefit/loss aur automatic result ke saath record hote hain. Exact broker margin sirf broker quote se milta hai."
        )
        strategy_note.setWordWrap(True); layout.addWidget(strategy_note)
        self.strategy_table = QTableWidget(0, 14)
        self.strategy_table.setHorizontalHeaderLabels((
            "Date", "Index", "Cutie name", "Structure", "Regime", "Bias", "Entry spot", "Payoff risk reserve",
            "Max benefit", "Max loss", "Model P&L", "Status", "Outcome", "Expiry",
        ))
        self.strategy_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.strategy_table.setMinimumHeight(250)
        layout.addWidget(self.strategy_table)
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
        strategies = self.db.get_strategy_trades(limit=1000)
        self.strategy_table.setRowCount(len(strategies))
        for row, item in enumerate(strategies):
            values = (
                item["trade_date"], item["symbol"], item["friendly_name"] or item["strategy_name"], item["strategy_name"],
                item["market_regime"] or "UNKNOWN", item["bias"], f"{float(item['entry_spot']):,.2f}",
                f"₹{float(item['capital_required']):,.2f} risk", f"₹{float(item['max_profit']):,.2f}",
                f"₹{float(item['max_loss']):,.2f}", f"₹{float(item['current_pnl']):,.2f}",
                item["status"], item["outcome"], item["expiry"],
            )
            for column, value in enumerate(values):
                self.strategy_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.strategy_table.resizeColumnsToContents()
        self.strategy_table.horizontalHeader().setStretchLastSection(True)

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
        review = self.db.get_trade_outcome_review(int(trade["id"]))
        automatic_review = (
            f"\n\nCutie automatic outcome review:\n{review['review_text']}\n"
            f"Solution / next reference: {review['solution_text']}\n"
            f"MFE ₹{float(review['mfe']):.2f} | MAE ₹{float(review['mae']):.2f}"
            if review else "\n\nAutomatic outcome review trade close hote hi generate hoga."
        )
        self.selected_details.setText(
            f"{trade['symbol']} {trade['strike'] or ''} {trade['option_type'] or ''} | "
            f"Status: {trade['status']} | Outcome: {trade['outcome'] or 'Monitoring'} | "
            f"Entry ₹{float(trade['entry']):.2f} | Stop ₹{float(trade['stoploss']):.2f} | "
            f"Target ₹{float(trade['target']):.2f} | P&L ₹{float(trade['pnl'] or 0):,.2f} | "
            f"AI decision: {trade['ai_decision'] or '-'}{automatic_review}"
        )

    def set_symbol_from_capture(self, _symbol: str) -> None:
        return

    def load_trade_plan(self, _plan: dict) -> None:
        self.load_trades()
