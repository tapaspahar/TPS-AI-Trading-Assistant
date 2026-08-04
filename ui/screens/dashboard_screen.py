from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ui.widgets.header import Header
from ui.widgets.information_panel import InformationPanel
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
from ui.pages.backtest_page import BacktestPage
from ui.pages.post_market_page import PostMarketPage
from ui.pages.replay_page import ReplayPage
from ui.pages.settings_page import SettingsPage
from ui.pages.equity_page import EquityPage
from ui.pages.auto_attempt_report_page import AutoAttemptReportPage
from ui.pages.about_help_page import AboutPage, HelpPage
from ui.pages.next_day_bias_page import NextDayBiasPage
from ui.widgets.glass_effects import add_glass_shadow


class DashboardScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardScreen")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(10)
        self.header = Header()
        add_glass_shadow(self.header)
        main_layout.addWidget(self.header)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)
        self.sidebar = Sidebar()
        add_glass_shadow(self.sidebar, blur=20, y_offset=3, opacity=75)
        body_layout.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        add_glass_shadow(self.stack, blur=25, y_offset=5, opacity=75)
        self.dashboardPage = DashboardPage()
        self.liveMarketPage = LiveMarketPage()
        self.optionsPage = OptionsPage()
        self.chartCapturePage = ChartCapturePage()
        self.journalPage = JournalPage()
        self.checklistPage = ChecklistPage()
        self.aiPage = AIPage()
        self.riskPage = RiskPage()
        self.reportsPage = ReportsPage()
        self.backtestPage = BacktestPage()
        self.postMarketPage = PostMarketPage()
        self.replayPage = ReplayPage()
        self.settingsPage = SettingsPage()
        self.equityPage = EquityPage()
        self.autoAttemptReportPage = AutoAttemptReportPage()
        self.aboutPage = AboutPage()
        self.helpPage = HelpPage()
        self.nextDayBiasPage = NextDayBiasPage()
        for page in (self.dashboardPage, self.liveMarketPage, self.optionsPage, self.chartCapturePage, self.journalPage,
                     self.checklistPage, self.aiPage, self.riskPage, self.reportsPage, self.settingsPage,
                     self.backtestPage, self.postMarketPage, self.replayPage, self.equityPage,
                     self.autoAttemptReportPage, self.aboutPage, self.helpPage, self.nextDayBiasPage):
            self.stack.addWidget(page)
        self.journalPage.trade_saved.connect(self.dashboardPage.refresh)
        self.journalPage.trade_saved.connect(self.reportsPage.refresh)
        self.journalPage.trade_saved.connect(self.optionsPage.update_plan_readiness)
        self.chartCapturePage.symbol_ready.connect(self.journalPage.set_symbol_from_capture)
        self.chartCapturePage.analysis_ready.connect(self.aiPage.load_chart_capture)
        self.aiPage.decision_ready.connect(self.handle_ai_decision)
        self.optionsPage.trade_plan_ready.connect(self.journalPage.load_trade_plan)
        self.optionsPage.trade_plan_ready.connect(self.riskPage.load_trade_plan)
        self.optionsPage.trade_plan_ready.connect(lambda _plan: self.show_page(4))
        self.journalPage.open_backtesting.connect(lambda: self.show_page(10))
        self.optionsPage.paper_trade_captured.connect(lambda _plan: self.journalPage.load_trades())
        self.optionsPage.paper_trade_captured.connect(lambda _plan: self.dashboardPage.refresh())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.journalPage.load_trades())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.dashboardPage.refresh())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.reportsPage.refresh())
        self.optionsPage.auto_attempt_saved.connect(self.autoAttemptReportPage.refresh)
        self.optionsPage.open_chart_capture.connect(lambda: self.show_page(3))
        self.settingsPage.live_connected.connect(self.start_default_nifty)
        for button, index in ((self.sidebar.dashboardButton, 0), (self.sidebar.liveMarketButton, 1),
                              (self.sidebar.optionsButton, 2), (self.sidebar.chartCaptureButton, 3),
                              (self.sidebar.journalButton, 4), (self.sidebar.checklistButton, 5),
                              (self.sidebar.aiButton, 6), (self.sidebar.riskButton, 7),
                              (self.sidebar.reportButton, 8), (self.sidebar.settingsButton, 9),
                              (self.sidebar.backtestButton, 10), (self.sidebar.postMarketButton, 11), (self.sidebar.replayButton, 12),
                              (self.sidebar.equityButton, 13), (self.sidebar.autoAttemptReportButton, 14),
                              (self.sidebar.aboutButton, 15), (self.sidebar.helpButton, 16),
                              (self.sidebar.nextDayBiasButton, 17)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout, 1)
        self.informationPanel = InformationPanel()
        add_glass_shadow(self.informationPanel, blur=16, y_offset=2, opacity=60)
        main_layout.addWidget(self.informationPanel)
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
        elif index == 2:
            self.optionsPage.prepare_live_workspace()
        elif index == 11:
            self.postMarketPage.refresh()
        elif index == 14:
            self.autoAttemptReportPage.refresh()
        elif index == 7:
            self.riskPage.refresh()
        self.stack.setCurrentIndex(index)

    def handle_ai_decision(self, context):
        self.optionsPage.set_chart_context(context)
        self.show_page(2)

    def start_default_nifty(self):
        self.liveMarketPage.select_symbol("NIFTY")
