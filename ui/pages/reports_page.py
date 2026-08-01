from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

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
