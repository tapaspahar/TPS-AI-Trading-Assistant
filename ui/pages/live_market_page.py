from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from services.angel_one_stream import AngelOneStream
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService
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
    overview_received = Signal(dict)
    overview_error = Signal(str)
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
        self.timeframe = QComboBox()
        self.timeframe.addItems(("5m", "15m", "1h", "1D", "All timeframes"))
        self.timeframe.currentTextChanged.connect(lambda _value: self.load_selected_timeframe())
        layout.addWidget(self.timeframe)
        self.multi_timeframe_button = QPushButton("Analyze Selected Timeframe")
        self.multi_timeframe_button.clicked.connect(self.load_selected_timeframe)
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
        overview_box = QGroupBox("Live Index & Current-Month Futures (updates every 10 seconds)")
        overview_grid = QGridLayout(overview_box)
        self.overview_cards = {
            **{symbol: DashboardCard(f"{symbol} Spot", "Waiting") for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")},
            **{f"{symbol} FUT": DashboardCard(f"{symbol} Future", "Loading") for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")},
        }
        for index, card in enumerate(self.overview_cards.values()):
            card.set_compact(True)
            overview_grid.addWidget(card, index // 3, index % 3)
        layout.addWidget(overview_box)
        layout.addStretch()
        self.tick_received.connect(self.show_tick)
        self.feed_status.connect(self.show_status)
        self.structure_received.connect(self.show_structure)
        self.structure_error.connect(self.show_structure_error)
        self.multi_timeframe_received.connect(self.show_multi_timeframe)
        self.multi_timeframe_error.connect(self.show_multi_timeframe_error)
        self.overview_received.connect(self.show_overview)
        self.overview_error.connect(self.show_overview_error)
        self.selected_symbol = None
        self.overview_loading = False
        self.future_contracts = {}
        self.overview_timer = QTimer(self)
        self.overview_timer.timeout.connect(self.load_market_overview)
        self.refresh_status()
        self.start_market_overview()

    def refresh_status(self):
        self.status.setText("Angel One: Connected (read-only)" if LiveSession.connected() else "Angel One: Not connected — connect from Settings first")

    def start_market_overview(self):
        if not LiveSession.connected():
            return
        self.load_market_overview()
        if not self.overview_timer.isActive():
            self.overview_timer.start(10000)

    def select_symbol(self, symbol):
        self.refresh_status()
        if not LiveSession.connected():
            return
        if LiveSession.stream:
            LiveSession.stream.stop()
        exchange_type, token = self.INSTRUMENTS[symbol]
        self.selected_symbol = (symbol, exchange_type, token)
        self.start_market_overview()
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
        self.load_selected_timeframe()

    def load_selected_timeframe(self):
        if not LiveSession.connected() or not self.selected_symbol:
            return
        if self.timeframe.currentText() == "All timeframes":
            self.load_multi_timeframe()
            return
        symbol, exchange_type, token = self.selected_symbol
        self.multi_timeframe_detail.setText(f"Loading {symbol} {self.timeframe.currentText()} chart analysis...")
        Thread(target=self._load_single_timeframe, args=(symbol, exchange_type, token, self.timeframe.currentText()), daemon=True).start()

    def _load_single_timeframe(self, symbol, exchange_type, token, label):
        exchange = "BSE" if exchange_type == 3 else "NSE"
        requests = {"5m": ("FIVE_MINUTE", 5), "15m": ("FIFTEEN_MINUTE", 15), "1h": ("ONE_HOUR", 60), "1D": ("ONE_DAY", 365)}
        try:
            interval, days = requests[label]
            result = analyze_candles(LiveSession.client.get_recent_candles(exchange, token, interval, days))
            result.update({"symbol": symbol, "timeframe": label})
            self.structure_received.emit(result)
        except (RuntimeError, ValueError) as error:
            self.multi_timeframe_error.emit(str(error))

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
        if result.get("timeframe"):
            self.multi_timeframe_detail.setText(
                f"{result['symbol']} {result['timeframe']} analysis: {result['state']}. "
                f"Support {result['support']:,.2f} | Resistance {result['resistance']:,.2f}."
            )

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
        short_state = result["context"].replace(" multi-timeframe alignment", "").replace(" multi-timeframe structure — wait for confirmation", " / Wait")
        self.cards["trend"].set_value(f"{short_state}\nAlignment: {result['alignment_score']}/100")
        self.cards["support"].set_value(f"{result['support']:,.2f}")
        self.cards["resistance"].set_value(f"{result['resistance']:,.2f}")
        self.multi_timeframe_detail.setText(
            f"{result['symbol']} multi-timeframe reading: {patterns}. "
            "Use the chart patterns as context; wait for live breakout/breakdown confirmation before acting."
        )

    def show_multi_timeframe_error(self, message):
        self.multi_timeframe_detail.setText(f"Multi-timeframe chart analysis unavailable: {message}")

    def load_market_overview(self):
        if not LiveSession.connected() or self.overview_loading:
            return
        self.overview_loading = True
        Thread(target=self._load_market_overview, daemon=True).start()

    def _load_market_overview(self):
        try:
            futures = self.future_contracts
            if not futures:
                service = OptionContractService()
                futures = {symbol: service.get_front_month_future(symbol) for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
            request = {"NSE": ["99926000", "99926009"], "BSE": ["99919000"]}
            for future in futures.values():
                request.setdefault(future["exchange"], []).append(future["token"])
            quotes = LiveSession.client.get_market_quotes(request)
            self.overview_received.emit({"quotes": {str(quote.get("symbolToken", quote.get("symboltoken", ""))): quote for quote in quotes}, "futures": futures})
        except RuntimeError as error:
            self.overview_error.emit(str(error))

    def show_overview(self, result):
        quotes, self.future_contracts = result["quotes"], result["futures"]
        token_map = {"99926000": "NIFTY", "99926009": "BANKNIFTY", "99919000": "SENSEX"}
        for token, symbol in token_map.items():
            quote = quotes.get(token)
            if not quote:
                self.overview_cards[symbol].set_value("Live quote unavailable")
                continue
            price = float(quote.get("ltp", 0) or 0)
            change = float(quote.get("netChange", 0) or 0)
            percent_change = float(quote.get("percentChange", 0) or 0)
            if change > 0:
                bias = "Bullish day bias"
            elif change < 0:
                bias = "Bearish day bias"
            else:
                bias = "Flat day bias"
            self.overview_cards[symbol].set_value(f"₹{price:,.2f}\n{bias} ({percent_change:+.2f}%)")
        for symbol, future in self.future_contracts.items():
            quote = quotes.get(future["token"])
            if quote:
                self.overview_cards[f"{symbol} FUT"].set_value(
                    f"Future ₹{float(quote.get('ltp', 0) or 0):,.2f}\nExpires {future['expiry'].strftime('%d %b')}"
                )
            else:
                self.overview_cards[f"{symbol} FUT"].set_value("Future quote unavailable")
        self.overview_loading = False

    def show_overview_error(self, _message):
        self.overview_loading = False
        for card in self.overview_cards.values():
            card.set_value("Overview temporarily unavailable")

    def show_status(self, status):
        self.status.setText(f"Angel One: {status}")

    def show_tick(self, tick):
        value = tick.get("last_traded_price") or tick.get("ltp") or tick.get("last_traded_price")
        if value is None:
            return
        price = float(value) / 100 if float(value) > 100000 else float(value)
        self.cards["ltp"].set_value(f"₹{price:,.2f}")
