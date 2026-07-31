from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout
)

from PySide6.QtCore import QTimer
from datetime import datetime


class Header(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("header")
        self.setFixedHeight(90)

        # Left Side
        self.title = QLabel("TPS AI Trading Assistant")
        self.title.setObjectName("title")

        self.subtitle = QLabel("Professional Trading Dashboard")
        self.subtitle.setObjectName("subtitle")

        left = QVBoxLayout()
        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        # Center
        self.market = QLabel("🟢 Market Status : Loading...")
        self.market.setObjectName("status")

        self.ai = QLabel("🤖 AI : Ready")
        self.ai.setObjectName("status")

        center = QVBoxLayout()
        center.addWidget(self.market)
        center.addWidget(self.ai)

        # Right
        self.clock = QLabel()
        self.clock.setObjectName("clock")

        self.user = QLabel("👤 Tapas")
        self.user.setObjectName("user")

        right = QVBoxLayout()
        right.addWidget(self.clock)
        right.addWidget(self.user)

        layout = QHBoxLayout(self)

        layout.addLayout(left)
        layout.addStretch()
        layout.addLayout(center)
        layout.addStretch()
        layout.addLayout(right)

        self.timer = QTimer()

        self.timer.timeout.connect(self.updateClock)

        self.timer.start(1000)

        self.updateClock()

    def updateClock(self):

        now = datetime.now()

        self.clock.setText(now.strftime("🕒 %d-%m-%Y   %H:%M:%S"))