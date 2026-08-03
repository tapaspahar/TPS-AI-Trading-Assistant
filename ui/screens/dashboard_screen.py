from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ui.widgets.header import Header
from ui.widgets.navigation.sidebar import Sidebar
from ui.pages.dashboard_page import DashboardPage
from ui.pages.live_market_page import LiveMarketPage
from ui.pages.options_page import OptionsPage
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
        self.optionsPage = OptionsPage()
        self.chartCapturePage = ChartCapturePage()
        self.journalPage = JournalPage()
        self.checklistPage = ChecklistPage()
        self.aiPage = AIPage()
        self.riskPage = RiskPage()
        self.reportsPage = ReportsPage()
        self.settingsPage = SettingsPage()
        for page in (self.dashboardPage, self.liveMarketPage, self.optionsPage, self.chartCapturePage, self.journalPage,
                     self.checklistPage, self.aiPage, self.riskPage, self.reportsPage, self.settingsPage):
            self.stack.addWidget(page)
        self.journalPage.trade_saved.connect(self.dashboardPage.refresh)
        self.journalPage.trade_saved.connect(self.reportsPage.refresh)
        self.chartCapturePage.symbol_ready.connect(self.journalPage.set_symbol_from_capture)
        self.chartCapturePage.analysis_ready.connect(self.aiPage.load_chart_capture)
        self.chartCapturePage.analysis_ready.connect(lambda _capture: self.show_page(6))
        self.aiPage.decision_ready.connect(self.optionsPage.set_chart_context)
        self.optionsPage.trade_plan_ready.connect(self.journalPage.load_trade_plan)
        self.optionsPage.trade_plan_ready.connect(lambda _plan: self.show_page(4))
        for button, index in ((self.sidebar.dashboardButton, 0), (self.sidebar.liveMarketButton, 1),
                              (self.sidebar.optionsButton, 2), (self.sidebar.chartCaptureButton, 3),
                              (self.sidebar.journalButton, 4), (self.sidebar.checklistButton, 5),
                              (self.sidebar.aiButton, 6), (self.sidebar.riskButton, 7),
                              (self.sidebar.reportButton, 8), (self.sidebar.settingsButton, 9)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout)
        QTimer.singleShot(0, self.settingsPage.auto_connect_saved_credentials)

    def show_page(self, index: int):
        self.sidebar.set_active(index)
        if index == 0:
            self.dashboardPage.refresh()
        elif index == 8:
            self.reportsPage.refresh()
        elif index == 1:
            self.liveMarketPage.refresh_status()
            self.liveMarketPage.start_market_overview()
        self.stack.setCurrentIndex(index)
