from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ui.widgets.header import Header
from ui.widgets.navigation.sidebar import Sidebar
from ui.pages.dashboard_page import DashboardPage
from ui.pages.live_market_page import LiveMarketPage
from ui.pages.chart_capture_page import ChartCapturePage
from ui.pages.journal_page import JournalPage
from ui.pages.checklist_page import ChecklistPage
from ui.pages.ai_page import AIPage
from ui.pages.risk_page import RiskPage
from ui.pages.reports_page import ReportsPage
from ui.pages.settings_page import SettingsPage


class DashboardScreen(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(Header())
        body_layout = QHBoxLayout()
        self.sidebar = Sidebar()
        body_layout.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.dashboardPage = DashboardPage()
        self.liveMarketPage = LiveMarketPage()
        self.chartCapturePage = ChartCapturePage()
        self.journalPage = JournalPage()
        self.checklistPage = ChecklistPage()
        self.aiPage = AIPage()
        self.riskPage = RiskPage()
        self.reportsPage = ReportsPage()
        self.settingsPage = SettingsPage()
        for page in (self.dashboardPage, self.liveMarketPage, self.chartCapturePage, self.journalPage,
                     self.checklistPage, self.aiPage, self.riskPage, self.reportsPage, self.settingsPage):
            self.stack.addWidget(page)
        self.journalPage.trade_saved.connect(self.dashboardPage.refresh)
        self.journalPage.trade_saved.connect(self.reportsPage.refresh)
        self.chartCapturePage.symbol_ready.connect(self.journalPage.set_symbol_from_capture)
        self.chartCapturePage.analysis_ready.connect(self.aiPage.load_chart_capture)
        self.chartCapturePage.analysis_ready.connect(lambda _capture: self.show_page(5))
        for button, index in ((self.sidebar.dashboardButton, 0), (self.sidebar.liveMarketButton, 1),
                              (self.sidebar.chartCaptureButton, 2), (self.sidebar.journalButton, 3),
                              (self.sidebar.checklistButton, 4), (self.sidebar.aiButton, 5),
                              (self.sidebar.riskButton, 6), (self.sidebar.reportButton, 7),
                              (self.sidebar.settingsButton, 8)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout)

    def show_page(self, index: int):
        if index == 0:
            self.dashboardPage.refresh()
        elif index == 7:
            self.reportsPage.refresh()
        elif index == 1:
            self.liveMarketPage.refresh_status()
        self.stack.setCurrentIndex(index)
