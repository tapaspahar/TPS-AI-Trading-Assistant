from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton


class Sidebar(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)

        buttons = [
            "🏠 Dashboard",
            "📈 Live Market",
            "📒 Trade Journal",
            "✅ Checklist",
            "🧠 AI Analysis",
            "🛡 Risk Manager",
            "📊 Reports",
            "⚙ Settings"
        ]

        for text in buttons:
            btn = QPushButton(text)
            btn.setObjectName("menuButton")
            layout.addWidget(btn)

        layout.addStretch()