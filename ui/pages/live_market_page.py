from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from services.angel_one_stream import AngelOneStream
from services.live_session import LiveSession
from engine.market_structure import analyze_candles
from engine.multi_timeframe_engine import analyze_multi_timeframe
from ui.widgets.cards.dashboard_card import DashboardCard


class LiveMarketPage(QWidget):
    """Read-only live decision workspace; no order controls are provided."""
    tick_received = Signal(dict)
    feed_status = Signal(str)
    structure_received = Signal(dict)
    structure_error = Signal(str)
    multi_timeframe_received = Signal(dict)
    multi_timeframe_error = Signal(str)
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
        self.multi_timeframe_button = QPushButton("Analyze 5m / 15m / 1h / 1D")
        self.multi_timeframe_button.clicked.connect(self.load_multi_timeframe)
        layout.addWidget(self.multi_timeframe_button)
        grid = QGridLayout()
        self.cards = {name: DashboardCard(title, "Waiting for live feed") for name, title in (
            ("ltp", "Live Price"), ("trend", "Market State"), ("support", "Support Zone"),
            ("resistance", "Resistance Zone"), ("breakout", "Breakout Condition"), ("breakdown", "Breakdown Condition"),
        )}
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addWidget(QLabel("Live feed values will auto-fill Decision Engine V2. This workspace is read-only and cannot place orders."))
        self.multi_timeframe_detail = QLabel("Select a live symbol, then run multi-timeframe chart analysis.")
        layout.addWidget(self.multi_timeframe_detail)
        layout.addStretch()
        self.refresh_status()
        self.tick_received.connect(self.show_tick)
        self.feed_status.connect(self.show_status)
        self.structure_received.connect(self.show_structure)
        self.structure_error.connect(self.show_structure_error)
        self.multi_timeframe_received.connect(self.show_multi_timeframe)
        self.multi_timeframe_error.connect(self.show_multi_timeframe_error)
        self.selected_symbol = None

    def refresh_status(self):
        self.status.setText("Angel One: Connected (read-only)" if LiveSession.connected() else "Angel One: Not connected — connect from Settings first")

    def select_symbol(self, symbol):
        self.refresh_status()
        if not LiveSession.connected():
            return
        if LiveSession.stream:
            LiveSession.stream.stop()
        exchange_type, token = self.INSTRUMENTS[symbol]
        self.selected_symbol = (symbol, exchange_type, token)
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
        Thread(target=self.load_market_structure, args=(symbol, exchange_type, token), daemon=True).start()

    def load_market_structure(self, symbol, exchange_type, token):
        exchange = "BSE" if exchange_type == 3 else "NSE"
        try:
            candles = LiveSession.client.get_recent_candles(exchange, token)
            result = analyze_candles(candles)
            result["symbol"] = symbol
        except (RuntimeError, ValueError) as error:
            self.structure_error.emit(str(error))
            return
        self.structure_received.emit(result)

    def show_structure(self, result):
        self.cards["trend"].set_value(result["state"])
        self.cards["support"].set_value(f"{result['support']:,.2f}")
        self.cards["resistance"].set_value(f"{result['resistance']:,.2f}")
        self.cards["breakout"].set_value(
            f"5m close > {result['breakout_level']:,.2f}\n{result['volume_condition']}"
        )
        self.cards["breakdown"].set_value(
            f"5m close < {result['breakdown_level']:,.2f}\n{result['volume_condition']}"
        )
        self.status.setText(f"Angel One: {result['symbol']} levels refreshed from {result['candle_count']} 5m candles")

    def show_structure_error(self, message):
        self.cards["trend"].set_value("Structure unavailable")
        self.cards["support"].set_value("No reliable level")
        self.cards["resistance"].set_value("No reliable level")
        self.status.setText(f"Angel One: live price connected; candle levels unavailable ({message})")

    def load_multi_timeframe(self):
        if not LiveSession.connected() or not self.selected_symbol:
            self.multi_timeframe_detail.setText("Select NIFTY, BANKNIFTY, or SENSEX after Angel One connects first.")
            return
        symbol, exchange_type, token = self.selected_symbol
        self.multi_timeframe_detail.setText(f"Loading {symbol} 5m, 15m, 1h and 1D chart history…")
        Thread(target=self._load_multi_timeframe, args=(symbol, exchange_type, token), daemon=True).start()

    def _load_multi_timeframe(self, symbol, exchange_type, token):
        exchange = "BSE" if exchange_type == 3 else "NSE"
        requests = {"5m": ("FIVE_MINUTE", 5), "15m": ("FIFTEEN_MINUTE", 15), "1h": ("ONE_HOUR", 60), "1D": ("ONE_DAY", 365)}
        try:
            candles = {
                label: LiveSession.client.get_recent_candles(exchange, token, interval, days)
                for label, (interval, days) in requests.items()
            }
            result = analyze_multi_timeframe(candles)
            result["symbol"] = symbol
        except (RuntimeError, ValueError) as error:
            self.multi_timeframe_error.emit(str(error))
            return
        self.multi_timeframe_received.emit(result)

    def show_multi_timeframe(self, result):
        patterns = " | ".join(f"{name}: {data['state'].replace(' structure', '')}, {data['pattern']}" for name, data in result["timeframes"].items())
        self.cards["trend"].set_value(f"{result['context']}\n{result['alignment_score']}/100")
        self.cards["support"].set_value(f"Multi-TF {result['support']:,.2f}")
        self.cards["resistance"].set_value(f"Multi-TF {result['resistance']:,.2f}")
        self.multi_timeframe_detail.setText(f"{result['symbol']}: {patterns}")

    def show_multi_timeframe_error(self, message):
        self.multi_timeframe_detail.setText(f"Multi-timeframe chart analysis unavailable: {message}")

    def show_status(self, status):
        self.status.setText(f"Angel One: {status}")

    def show_tick(self, tick):
        value = tick.get("last_traded_price") or tick.get("ltp") or tick.get("last_traded_price")
        if value is None:
            return
        price = float(value) / 100 if float(value) > 100000 else float(value)
        self.cards["ltp"].set_value(f"₹{price:,.2f}")
