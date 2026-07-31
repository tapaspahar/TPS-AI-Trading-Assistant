from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout
)

from ui.widgets.header import Header
from ui.widgets.navigation.sidebar import Sidebar
from ui.widgets.cards.dashboard_card import DashboardCard


class DashboardScreen(QWidget):

    def __init__(self):
        super().__init__()

        mainLayout = QVBoxLayout(self)

        # Header
        mainLayout.addWidget(Header())

        # Body Layout
        bodyLayout = QHBoxLayout()

        # Sidebar
        bodyLayout.addWidget(Sidebar())

        # Dashboard Area
        dashboardLayout = QVBoxLayout()

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)

        grid.addWidget(DashboardCard("📈 Market Trend", "Waiting..."), 0, 0)
        grid.addWidget(DashboardCard("💰 Today's P&L", "₹0"), 0, 1)
        grid.addWidget(DashboardCard("🎯 AI Confidence", "-- %"), 0, 2)

        grid.addWidget(DashboardCard("❤️ Psychology", "Ready"), 1, 0)
        grid.addWidget(DashboardCard("🛡 Risk Score", "Safe"), 1, 1)
        grid.addWidget(DashboardCard("📊 Today's Trades", "0"), 1, 2)

        dashboardLayout.addLayout(grid)
        dashboardLayout.addStretch()

        bodyLayout.addLayout(dashboardLayout)

        mainLayout.addLayout(bodyLayout)