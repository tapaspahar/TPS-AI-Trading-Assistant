from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton


class Sidebar(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)

        self.dashboardButton = QPushButton("🏠 Dashboard")
        self.liveMarketButton = QPushButton("📈 Live Market")
        self.journalButton = QPushButton("📒 Trade Journal")
        self.checklistButton = QPushButton("✅ Checklist")
        self.aiButton = QPushButton("🧠 AI Analysis")
        self.riskButton = QPushButton("🛡 Risk Manager")
        self.reportButton = QPushButton("📊 Reports")
        self.settingsButton = QPushButton("⚙ Settings")

        buttons = [
            self.dashboardButton,
            self.liveMarketButton,
            self.journalButton,
            self.checklistButton,
            self.aiButton,
            self.riskButton,
            self.reportButton,
            self.settingsButton
        ]

        for button in buttons:
            button.setObjectName("menuButton")
            layout.addWidget(button)

        layout.addStretch()