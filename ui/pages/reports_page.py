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
        self.report.setText(
            f"Recorded trades: {summary['trades']}\n"
            f"Net P&L: ₹{summary['pnl']:,.2f}\n"
            f"Winning trades: {summary['winning_trades']}\n"
            f"Win rate: {summary['win_rate']:.1f}%\n"
            f"Average AI confidence: {summary['average_ai']:.1f}%"
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
