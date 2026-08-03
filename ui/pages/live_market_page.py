from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from services.angel_one_stream import AngelOneStream
from services.live_session import LiveSession
from ui.widgets.cards.dashboard_card import DashboardCard


class LiveMarketPage(QWidget):
    """Read-only live decision workspace; no order controls are provided."""
    tick_received = Signal(dict)
    feed_status = Signal(str)
    # SmartAPI index mappings: (WebSocket exchange type, current index token).
    # Angel One uses exchange type 1 for NSE cash-market indices and 3 for BSE.
    INSTRUMENTS = {
        "NIFTY": (1, "99926000"),
        "BANKNIFTY": (1, "99926009"),
        "SENSEX": (3, "99919000"),
    }

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
        self.tick_received.connect(self.show_tick)
        self.feed_status.connect(self.show_status)

    def refresh_status(self):
        self.status.setText("Angel One: Connected (read-only)" if LiveSession.connected() else "Angel One: Not connected — connect from Settings first")

    def select_symbol(self, symbol):
        self.refresh_status()
        if not LiveSession.connected():
            return
        if LiveSession.stream:
            LiveSession.stream.stop()
        exchange_type, token = self.INSTRUMENTS[symbol]
        LiveSession.stream = AngelOneStream(LiveSession.client, self.tick_received.emit, self.feed_status.emit)
        try:
            LiveSession.stream.start(exchange_type, token)
        except RuntimeError as error:
            self.status.setText(str(error))
            return
        self.cards["ltp"].set_value(f"{symbol} subscribing…")
        self.cards["trend"].set_value("Connecting live feed…")
        self.cards["support"].set_value("Waiting for candles")
        self.cards["resistance"].set_value("Waiting for candles")
        self.cards["breakout"].set_value("5m close + volume confirmation")
        self.cards["breakdown"].set_value("5m close + volume confirmation")

    def show_status(self, status):
        self.status.setText(f"Angel One: {status}")

    def show_tick(self, tick):
        value = tick.get("last_traded_price") or tick.get("ltp") or tick.get("last_traded_price")
        if value is None:
            return
        price = float(value) / 100 if float(value) > 100000 else float(value)
        self.cards["ltp"].set_value(f"₹{price:,.2f}")
