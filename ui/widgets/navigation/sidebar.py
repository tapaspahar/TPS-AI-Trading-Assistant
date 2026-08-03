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
        self.optionsButton = QPushButton("◉  Options Workspace")
        self.chartCaptureButton = QPushButton("▣  Chart Capture")
        self.journalButton = QPushButton("▤  Trade Journal")
        self.checklistButton = QPushButton("✓  Checklist")
        self.aiButton = QPushButton("✦  AI Analysis")
        self.riskButton = QPushButton("◈  Risk Manager")
        self.reportButton = QPushButton("▥  Reports")
        self.settingsButton = QPushButton("⚙  Settings")
        self.buttons = (self.dashboardButton, self.liveMarketButton, self.optionsButton, self.chartCaptureButton, self.journalButton,
                        self.checklistButton, self.aiButton, self.riskButton, self.reportButton, self.settingsButton)
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
        button = self.menu_group.button(index)
        if button:
            button.setChecked(True)
