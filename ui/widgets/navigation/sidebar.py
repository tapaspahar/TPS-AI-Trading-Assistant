from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton


class Sidebar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        self.dashboardButton = QPushButton("Dashboard")
        self.liveMarketButton = QPushButton("Market Snapshot")
        self.chartCaptureButton = QPushButton("Chart Capture")
        self.journalButton = QPushButton("Trade Journal")
        self.checklistButton = QPushButton("Checklist")
        self.aiButton = QPushButton("AI Analysis")
        self.riskButton = QPushButton("Risk Manager")
        self.reportButton = QPushButton("Reports")
        self.settingsButton = QPushButton("Settings")
        for button in (self.dashboardButton, self.liveMarketButton, self.chartCaptureButton, self.journalButton,
                       self.checklistButton, self.aiButton, self.riskButton, self.reportButton, self.settingsButton):
            button.setObjectName("menuButton")
            layout.addWidget(button)
        layout.addStretch()
