from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget
)

from ui.widgets.header import Header
from ui.widgets.navigation.sidebar import Sidebar

from ui.pages.dashboard_page import DashboardPage
from ui.pages.live_market_page import LiveMarketPage
from ui.pages.journal_page import JournalPage
from ui.pages.checklist_page import ChecklistPage
from ui.pages.ai_page import AIPage
from ui.pages.risk_page import RiskPage
from ui.pages.reports_page import ReportsPage
from ui.pages.settings_page import SettingsPage


class DashboardScreen(QWidget):

    def __init__(self):

        super().__init__()

        mainLayout = QVBoxLayout(self)

        header = Header()
        mainLayout.addWidget(header)

        bodyLayout = QHBoxLayout()

        self.sidebar = Sidebar()

        bodyLayout.addWidget(self.sidebar)

        self.stack = QStackedWidget()

        self.dashboardPage = DashboardPage()
        self.liveMarketPage = LiveMarketPage()
        self.journalPage = JournalPage()
        self.checklistPage = ChecklistPage()
        self.aiPage = AIPage()
        self.riskPage = RiskPage()
        self.reportsPage = ReportsPage()
        self.settingsPage = SettingsPage()

        self.stack.addWidget(self.dashboardPage)
        self.stack.addWidget(self.liveMarketPage)
        self.stack.addWidget(self.journalPage)
        self.stack.addWidget(self.checklistPage)
        self.stack.addWidget(self.aiPage)
        self.stack.addWidget(self.riskPage)
        self.stack.addWidget(self.reportsPage)
        self.stack.addWidget(self.settingsPage)

        bodyLayout.addWidget(self.stack)

        mainLayout.addLayout(bodyLayout)

        self.sidebar.dashboardButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(0)
        )

        self.sidebar.liveMarketButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(1)
        )

        self.sidebar.journalButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(2)
        )

        self.sidebar.checklistButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(3)
        )

        self.sidebar.aiButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(4)
        )

        self.sidebar.riskButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(5)
        )

        self.sidebar.reportButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(6)
        )

        self.sidebar.settingsButton.clicked.connect(
            lambda: self.stack.setCurrentIndex(7)
        )