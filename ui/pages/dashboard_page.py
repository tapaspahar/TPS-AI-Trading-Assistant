from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout

from ui.widgets.cards.dashboard_card import DashboardCard


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)

        grid.addWidget(DashboardCard("📈 Market Trend", "Waiting..."), 0, 0)
        grid.addWidget(DashboardCard("💰 Today's P&L", "₹0"), 0, 1)
        grid.addWidget(DashboardCard("🎯 AI Confidence", "-- %"), 0, 2)

        grid.addWidget(DashboardCard("❤️ Psychology", "Ready"), 1, 0)
        grid.addWidget(DashboardCard("🛡 Risk Score", "Safe"), 1, 1)
        grid.addWidget(DashboardCard("📊 Today's Trades", "0"), 1, 2)

        layout.addLayout(grid)
        layout.addStretch()