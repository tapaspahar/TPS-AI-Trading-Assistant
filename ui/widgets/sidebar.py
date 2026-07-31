from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton


class SideBar(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)

        buttons = [
            "🏠 Dashboard",
            "📒 Trade Journal",
            "✅ Checklist",
            "🛡 Risk Manager",
            "📊 Reports",
            "⚙ Settings"
        ]

        for text in buttons:
            layout.addWidget(QPushButton(text))

        layout.addStretch()