from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QScrollArea, QVBoxLayout, QPushButton, QWidget


class Sidebar(QFrame):
    NAV_BULLET = "◆"

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(236)
        shell_layout = QVBoxLayout(self)
        shell_layout.setContentsMargins(6, 12, 6, 12)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("sidebarScroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            "QScrollArea#sidebarScroll { background: transparent; border: none; }"
            "QScrollArea#sidebarScroll > QWidget > QWidget { background: transparent; }"
        )
        self.menu_widget = QWidget()
        self.menu_widget.setObjectName("sidebarMenu")
        layout = QVBoxLayout(self.menu_widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(5)
        nav = lambda label: QPushButton(f"{self.NAV_BULLET}  {label}")
        self.dashboardButton = nav("Dashboard")
        self.liveMarketButton = nav("Market Snapshot")
        self.optionsButton = nav("Options Workspace")
        self.journalButton = nav("Trade Journal")
        self.reportButton = nav("Reports")
        self.settingsButton = nav("Settings")
        self.backtestButton = nav("Backtesting")
        self.replayButton = nav("Candle Replay")
        self.postMarketTpsAnalysisButton = nav("Post Market Analysis of TPS")
        self.selfDevelopmentButton = nav("AI Development Center")
        self.equityButton = nav("Equity Research")
        self.autoAttemptReportButton = nav("Auto Attempt Report")
        self.notificationCenterButton = nav("Notification Center")
        self.recoveryCenterButton = nav("Overtrading Protection")
        self.aboutButton = nav("About")
        self.helpButton = nav("Help")
        self.powerfulEngineButton = nav("Powerful Engine")
        self.casAnalysisButton = nav("CAS Analysis")
        self.optionStrategiesButton = nav("Option Strategies")
        self.strategyTradesButton = nav("Strategy Trades")
        self.expiryObservationButton = nav("Expiry After 3 PM")
        self.executionControlButton = nav("Broker Execution")
        self.optionsAlgoButton = nav("Options Algo Trading")
        self.cutieCommandButton = nav("Cutie AI Commands")
        self.indexMarketAnalysisButton = nav("Index Market Analysis")
        self.gapProbabilityButton = nav("3:20 + 3:40 Gap Probability")
        self.autoOpportunityButton = nav("Auto Opportunity Radar")
        self.trendMemoryButton = nav("Trend Memory Monitor")
        self.scalperButton = nav("Options Scalper")
        # Release 1.5.2 compact navigation. Existing named buttons remain as
        # route identities for compatibility, while only five workspace
        # launchers are visible; related pages live in tabs inside each hub.
        self.marketCenterButton = nav("Market Intelligence")
        self.tradingCenterButton = nav("Trading & Strategies")
        self.reportsCenterButton = nav("Reports & Learning")
        self.controlsCenterButton = nav("Controls & Settings")
        self.buttons = (
            self.dashboardButton, self.marketCenterButton, self.tradingCenterButton,
            self.reportsCenterButton, self.controlsCenterButton,
        )
        # Stack page numbers intentionally remain stable even when the visual
        # menu order changes.  This prevents the wrong sidebar item being
        # highlighted after an automatic screen change.
        self.page_buttons = {
            0: self.dashboardButton,
            1: self.marketCenterButton,
            2: self.tradingCenterButton,
            4: self.reportsCenterButton,
            9: self.controlsCenterButton,
        }
        self.menu_group = QButtonGroup(self)
        self.menu_group.setExclusive(True)
        for index, button in enumerate(self.buttons):
            button.setObjectName("menuButton")
            button.setCheckable(True)
            button.setFixedHeight(44)
            self.menu_group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch()
        self.menu_widget.setMinimumHeight(len(self.buttons) * 49 + 4)
        self.scroll.setWidget(self.menu_widget)
        shell_layout.addWidget(self.scroll)
        self.dashboardButton.setChecked(True)

    def set_active(self, index: int):
        button = self.page_buttons.get(index)
        if button:
            button.setChecked(True)
            self.scroll.ensureWidgetVisible(button, 0, 16)

    def set_notification_count(self, count: int):
        suffix = f" ({int(count)})" if count else ""
        self.notificationCenterButton.setText(f"{self.NAV_BULLET}  Notification Center{suffix}")
        self.reportsCenterButton.setText(f"{self.NAV_BULLET}  Reports & Learning{suffix}")
