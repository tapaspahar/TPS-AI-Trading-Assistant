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
        self.chartCaptureButton = nav("Chart Capture")
        self.aiButton = nav("AI Analysis")
        self.optionsButton = nav("Options Workspace")
        self.journalButton = nav("Trade Journal")
        self.checklistButton = nav("Checklist")
        self.riskButton = nav("Risk Manager")
        self.reportButton = nav("Reports")
        self.settingsButton = nav("Settings")
        self.backtestButton = nav("Backtesting")
        self.replayButton = nav("Candle Replay")
        self.postMarketButton = nav("Post-Market Report")
        self.equityButton = nav("Equity Research")
        self.autoAttemptReportButton = nav("Auto Attempt Report")
        self.aboutButton = nav("About")
        self.helpButton = nav("Help")
        # Keep the visual journey in the same order a trader uses the app:
        # market context -> chart confirmation -> AI evaluation -> option plan -> journal.
        self.buttons = (
            self.dashboardButton, self.liveMarketButton, self.equityButton, self.chartCaptureButton,
            self.aiButton, self.optionsButton, self.autoAttemptReportButton, self.journalButton,
            self.checklistButton, self.riskButton, self.reportButton, self.backtestButton, self.replayButton,
            self.postMarketButton, self.settingsButton, self.aboutButton, self.helpButton,
        )
        # Stack page numbers intentionally remain stable even when the visual
        # menu order changes.  This prevents the wrong sidebar item being
        # highlighted after an automatic screen change.
        self.page_buttons = {
            0: self.dashboardButton,
            1: self.liveMarketButton,
            2: self.optionsButton,
            3: self.chartCaptureButton,
            4: self.journalButton,
            5: self.checklistButton,
            6: self.aiButton,
            7: self.riskButton,
            8: self.reportButton,
            9: self.settingsButton,
            10: self.backtestButton,
            11: self.postMarketButton,
            12: self.replayButton,
            13: self.equityButton,
            14: self.autoAttemptReportButton,
            15: self.aboutButton,
            16: self.helpButton,
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
