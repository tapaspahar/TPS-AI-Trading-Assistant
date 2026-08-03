from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.database_manager import Database


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Journal Report"))
        self.report = QLabel()
        self.report.setWordWrap(True)
        layout.addWidget(self.report)
        refresh = QPushButton("Refresh Report")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        export = QPushButton("Export Journal to CSV")
        export.clicked.connect(self.export_csv)
        layout.addWidget(export)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        summary = self.db.get_summary()
        outcomes = self.db.get_ai_outcome_report()
        self.report.setText(
            f"Recorded trades: {summary['trades']}\n"
            f"Net P&L: ₹{summary['pnl']:,.2f}\n"
            f"Winning trades: {summary['winning_trades']}\n"
            f"Win rate: {summary['win_rate']:.1f}%\n"
            f"Average AI confidence: {summary['average_ai']:.1f}%\n\n"
            f"AI Outcome Review\n"
            f"Open trades: {outcomes['open_trades']} | Closed trades: {outcomes['closed_trades']}\n"
            f"Target hit: {outcomes['target_hits']} | Stop loss hit: {outcomes['stoploss_hits']} | Manual exit: {outcomes['manual_exits']}\n"
            f"Target vs stop-loss accuracy: {outcomes['target_vs_stop_accuracy']:.1f}%\n"
            "A stop loss does not prove the AI was wrong; review the chart, timing, volatility, news, liquidity and execution before changing the rules."
       )

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Trade Journal", "trade_journal.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            count = self.db.export_csv(path)
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} trade(s) to CSV.")
