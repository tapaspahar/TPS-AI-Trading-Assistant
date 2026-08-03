from PySide6.QtWidgets import QButtonGroup, QFrame, QVBoxLayout, QPushButton


class Sidebar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(236)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(5)
        self.dashboardButton = QPushButton("▦  Dashboard")
        self.liveMarketButton = QPushButton("◈  Market Snapshot")
        self.chartCaptureButton = QPushButton("▣  Chart Capture")
        self.aiButton = QPushButton("✦  AI Analysis")
        self.optionsButton = QPushButton("◉  Options Workspace")
        self.journalButton = QPushButton("▤  Trade Journal")
        self.checklistButton = QPushButton("✓  Checklist")
        self.riskButton = QPushButton("◈  Risk Manager")
        self.reportButton = QPushButton("▥  Reports")
        self.settingsButton = QPushButton("⚙  Settings")
        self.backtestButton = QPushButton("Backtesting")
        self.postMarketButton = QPushButton("Post-Market Report")
        # Keep the visual journey in the same order a trader uses the app:
        # market context -> chart confirmation -> AI evaluation -> option plan -> journal.
        self.buttons = (
            self.dashboardButton, self.liveMarketButton, self.chartCaptureButton,
            self.aiButton, self.optionsButton, self.journalButton,
            self.checklistButton, self.riskButton, self.reportButton, self.backtestButton, self.postMarketButton, self.settingsButton,
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
        }
        self.menu_group = QButtonGroup(self)
        self.menu_group.setExclusive(True)
        for index, button in enumerate(self.buttons):
            button.setObjectName("menuButton")
            button.setCheckable(True)
            self.menu_group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch()
        self.dashboardButton.setChecked(True)

    def set_active(self, index: int):
        button = self.page_buttons.get(index)
        if button:
            button.setChecked(True)
