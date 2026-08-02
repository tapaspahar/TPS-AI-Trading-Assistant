from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from services.live_session import LiveSession
from ui.widgets.cards.dashboard_card import DashboardCard


class LiveMarketPage(QWidget):
    """Read-only live decision workspace; no order controls are provided."""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QGridLayout()
        for index, symbol in enumerate(("NIFTY", "BANKNIFTY", "SENSEX")):
            button = QPushButton(symbol)
            button.clicked.connect(lambda _checked=False, name=symbol: self.select_symbol(name))
            buttons.addWidget(button, 0, index)
        layout.addLayout(buttons)
        grid = QGridLayout()
        self.cards = {name: DashboardCard(title, "Waiting for live feed") for name, title in (
            ("ltp", "Live Price"), ("trend", "Market State"), ("support", "Support Zone"),
            ("resistance", "Resistance Zone"), ("breakout", "Breakout Condition"), ("breakdown", "Breakdown Condition"),
        )}
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addWidget(QLabel("Live feed values will auto-fill Decision Engine V2. This workspace is read-only and cannot place orders."))
        layout.addStretch()
        self.refresh_status()

    def refresh_status(self):
        self.status.setText("Angel One: Connected (read-only)" if LiveSession.connected() else "Angel One: Not connected — connect from Settings first")

    def select_symbol(self, symbol):
        self.refresh_status()
        if not LiveSession.connected():
            return
        self.cards["ltp"].set_value(f"{symbol} selected")
        self.cards["trend"].set_value("Connecting live feed…")
        self.cards["support"].set_value("Waiting for candles")
        self.cards["resistance"].set_value("Waiting for candles")
        self.cards["breakout"].set_value("5m close + volume confirmation")
        self.cards["breakdown"].set_value("5m close + volume confirmation")
