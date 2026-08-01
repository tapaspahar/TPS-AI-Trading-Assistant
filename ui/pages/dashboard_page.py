from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from core.database_manager import Database
from ui.widgets.cards.dashboard_card import DashboardCard


class DashboardPage(QWidget):
    """Overview of the locally recorded trading journal."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        self.cards = {
            "market": DashboardCard("Market Trend", "Offline"),
            "pnl": DashboardCard("Journal P&L", "₹0.00"),
            "ai": DashboardCard("Average AI Confidence", "0%"),
            "win_rate": DashboardCard("Win Rate", "0%"),
            "risk": DashboardCard("Risk Status", "Review each trade"),
            "trades": DashboardCard("Recorded Trades", "0"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        refresh_button = QPushButton("Refresh Dashboard")
        refresh_button.clicked.connect(self.refresh)
        layout.addWidget(refresh_button)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        summary = self.db.get_summary()
        self.cards["pnl"].set_value(f"₹{summary['pnl']:,.2f}")
        self.cards["ai"].set_value(f"{summary['average_ai']:.0f}%")
        self.cards["win_rate"].set_value(f"{summary['win_rate']:.1f}%")
        self.cards["trades"].set_value(summary["trades"])
        self.cards["risk"].set_value("Safe" if summary["trades"] == 0 or summary["pnl"] >= 0 else "Review loss")
