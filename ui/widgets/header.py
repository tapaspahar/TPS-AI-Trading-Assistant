from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.market_session import IST, format_remaining, market_session


class Header(QFrame):
    settings_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("header")
        self.setFixedHeight(90)

        self.title = QLabel("TPS AI Trading Assistant")
        self.title.setObjectName("title")
        badge = QLabel("TPS")
        badge.setObjectName("appBadge")
        badge.setFixedSize(46, 46)
        self.subtitle = QLabel("Professional Trading Dashboard • UI Design: Pooja Pandey (Cutie)")
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setText("Professional Trading Dashboard")
        left = QVBoxLayout()
        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(badge)
        brand.addLayout(left)

        self.market = QLabel("Market Status: Loading…")
        self.market.setObjectName("status")
        self.ai = QLabel("AI: Ready")
        self.ai.setObjectName("status")
        center = QVBoxLayout()
        center.addWidget(self.market)
        center.addWidget(self.ai)

        self.clock = QLabel()
        self.clock.setObjectName("clock")
        self.settingsButton = QPushButton("⚙")
        self.settingsButton.setObjectName("headerSettingsButton")
        self.settingsButton.setFixedSize(36, 36)
        self.settingsButton.setToolTip("Open Settings")
        self.settingsButton.setAccessibleName("Open Settings")
        self.settingsButton.clicked.connect(self.settings_requested.emit)
        self.user = QLabel("Tapas")
        self.user.setObjectName("user")
        clock_row = QHBoxLayout()
        clock_row.setContentsMargins(0, 0, 0, 0)
        clock_row.setSpacing(8)
        clock_row.addWidget(self.clock)
        clock_row.addWidget(self.settingsButton)
        right = QVBoxLayout()
        right.addLayout(clock_row)
        right.addWidget(self.user)

        layout = QHBoxLayout(self)
        layout.addLayout(brand)
        layout.addStretch()
        layout.addLayout(center)
        layout.addStretch()
        layout.addLayout(right)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateClock)
        self.timer.start(1000)
        self.updateClock()

    def updateClock(self):
        now = datetime.now(IST)
        session = market_session(now)
        remaining = format_remaining(session["deadline"] - now)
        self.clock.setText(now.strftime("%d-%m-%Y   %H:%M:%S IST"))
        self.market.setText(f"Market Status: {session['label']} in {remaining}")
