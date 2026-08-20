from datetime import datetime
from threading import Thread

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from services.broker_stream import create_broker_stream
from services.broker_registry import broker_definition
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService
from services.market_snapshot_recorder import MarketSnapshotRecorder
from core.database_manager import Database
from engine.market_structure import analyze_candles
from engine.market_environment import classify_vix_percentile
from engine.multi_timeframe_engine import analyze_multi_timeframe
from engine.level_proximity import classify_level_proximity
from core.market_session import market_session
from ui.widgets.cards.dashboard_card import DashboardCard


class LiveMarketPage(QWidget):
    """Read-only live decision workspace; no order controls are provided."""
    tick_received = Signal(dict)
    feed_status = Signal(str)
    structure_received = Signal(dict)
    structure_error = Signal(dict)
    multi_timeframe_received = Signal(dict)
    multi_timeframe_error = Signal(str)
    overview_received = Signal(dict)
    overview_error = Signal(str)
    snapshot_saved = Signal(str)
    snapshot_error = Signal(str)
    guard_alert = Signal(object)
    level_alert = Signal(object)
    # SmartAPI index mappings: (WebSocket exchange type, current index token).
    # Angel One uses exchange type 1 for NSE cash-market indices and 3 for BSE.
    INSTRUMENTS = {
        "NIFTY": (1, "99926000"),
        "BANKNIFTY": (1, "99926009"),
        "SENSEX": (3, "99919000"),
    }

    def __init__(self):
        super().__init__()
        self.setObjectName("liveMarketContent")
        # Keep the information-dense market cards clean across every visual
        # theme. Some style overlays add large padding/margins which otherwise
        # pushes multi-line values outside compact cards.
        self.setStyleSheet("""
            QWidget#liveMarketContent QFrame#dashboardCard[marketSnapshotCard="true"] {
                padding: 3px;
                margin: 0px;
            }
            QWidget#liveMarketContent QFrame#dashboardCard[marketSnapshotCard="true"] QLabel#cardValue[density="compact"] {
                font-size: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(5)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QGridLayout()
        buttons.setHorizontalSpacing(8)
        for index, symbol in enumerate(("NIFTY", "BANKNIFTY", "SENSEX")):
            button = QPushButton(symbol)
            button.setFixedHeight(32)
            button.clicked.connect(lambda _checked=False, name=symbol: self.select_symbol(name))
            buttons.addWidget(button, 0, index)
        layout.addLayout(buttons)
        self.timeframe = QComboBox()
        self.timeframe.setFixedHeight(32)
        self.timeframe.addItems(("5m", "15m", "1h", "1D", "All timeframes"))
        self.timeframe.currentTextChanged.connect(lambda _value: self.load_selected_timeframe())
        layout.addWidget(self.timeframe)
        self.multi_timeframe_button = QPushButton("Analyze Selected Timeframe")
        self.multi_timeframe_button.setFixedHeight(32)
        self.multi_timeframe_button.clicked.connect(self.load_selected_timeframe)
        layout.addWidget(self.multi_timeframe_button)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.cards = {name: DashboardCard(title, "Waiting for live feed") for name, title in (
            ("ltp", "Live Price"), ("trend", "Market State"), ("support", "Support Zone"),
            ("resistance", "Resistance Zone"), ("breakout", "Breakout Condition"), ("breakdown", "Breakdown Condition"),
        )}
        for index, card in enumerate(self.cards.values()):
            card.setProperty("marketSnapshotCard", True)
            card.set_compact(True)
            card.setFixedHeight(82)
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        self.multi_timeframe_detail = QLabel("Select a live symbol, then run multi-timeframe chart analysis.")
        layout.addWidget(self.multi_timeframe_detail)
        self.snapshot_status = QLabel("Snapshot recorder: waiting for a live symbol.")
        layout.addWidget(self.snapshot_status)
        self.capture_snapshot_button = QPushButton("Save Market Snapshot Now (5m + 15m)")
        self.capture_snapshot_button.setFixedHeight(32)
        self.capture_snapshot_button.clicked.connect(lambda _checked=False: self.capture_market_snapshot())
        layout.addWidget(self.capture_snapshot_button)
        self.overview_box = QGroupBox("Live Index & Current-Month Futures (updates every 30 seconds)")
        self.overview_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.overview_grid = QGridLayout(self.overview_box)
        self.overview_grid.setContentsMargins(10, 18, 10, 8)
        self.overview_grid.setHorizontalSpacing(8)
        self.overview_grid.setVerticalSpacing(8)
        self.overview_cards = {
            **{symbol: DashboardCard(f"{symbol} Spot + Future", "Waiting") for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")},
            "INDIA VIX": DashboardCard("India VIX", "Loading live volatility"),
        }
        for card in self.overview_cards.values():
            card.setProperty("marketSnapshotCard", True)
            card.set_compact(True)
            card.setFixedHeight(104)
        self._layout_overview_cards()
        layout.addWidget(self.overview_box)
        layout.addStretch(1)
        self.tick_received.connect(self.show_tick)
        self.feed_status.connect(self.show_status)
        self.structure_received.connect(self.show_structure)
        self.structure_error.connect(self.show_structure_error)
        self.multi_timeframe_received.connect(self.show_multi_timeframe)
        self.multi_timeframe_error.connect(self.show_multi_timeframe_error)
        self.overview_received.connect(self.show_overview)
        self.overview_error.connect(self.show_overview_error)
        self.snapshot_saved.connect(self.show_snapshot_saved)
        self.snapshot_error.connect(self.show_snapshot_error)
        self.guard_alert.connect(self.show_guard_alert)
        self.selected_symbol = None
        self.selection_request = 0
        self.structure_cache = {}
        self.pending_level_candidates = {}
        self.current_levels = None
        self.last_level_state = None
        self.overview_loading = False
        self.future_contracts = {}
        self.vix_instrument = None
        self.vix_history = []
        self.overview_timer = QTimer(self)
        self.overview_timer.timeout.connect(self.load_market_overview)
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.capture_scheduled_snapshot)
        self.last_snapshot_bucket = None
        self.refresh_status()
        self.start_market_overview()

    def _layout_overview_cards(self):
        """Show each index's spot and future together in one collision-free row."""
        while self.overview_grid.count():
            item = self.overview_grid.takeAt(0)
            if item.widget():
                item.widget().setParent(self.overview_box)
        ordered_keys = ("NIFTY", "BANKNIFTY", "SENSEX", "INDIA VIX")
        for column, key in enumerate(ordered_keys):
            self.overview_grid.setColumnStretch(column, 1)
            self.overview_grid.addWidget(self.overview_cards[key], 0, column)
        self.overview_grid.invalidate()
        self.overview_box.updateGeometry()

    def refresh_status(self):
        broker = broker_definition(LiveSession.broker_id or "angel_one").name
        self.status.setText(f"{broker}: Connected (read-only)" if LiveSession.connected() else "Broker: Not connected — connect from Settings first")

    def start_market_overview(self):
        if not LiveSession.connected():
            return
        self.load_market_overview()
        if not self.overview_timer.isActive():
            # WebSocket remains the live-price source; the larger overview is
            # intentionally slower to avoid repeatedly timing out Angel One's
            # REST quote endpoint.
            self.overview_timer.start(30_000)

    def select_symbol(self, symbol):
        self.refresh_status()
        if not LiveSession.connected():
            return
        if LiveSession.stream:
            LiveSession.stream.stop()
        exchange_type, token = self.INSTRUMENTS[symbol]
        self.selection_request += 1
        request_id = self.selection_request
        self.selected_symbol = (symbol, exchange_type, token)
        self.current_levels = None
        self.last_level_state = None
        if not self.snapshot_timer.isActive():
            self.snapshot_timer.start(30_000)
        self.start_market_overview()
        LiveSession.stream = create_broker_stream(
            LiveSession.broker_id, LiveSession.client, self.tick_received.emit, self.feed_status.emit
        )
        try:
            LiveSession.stream.start(exchange_type, token)
        except RuntimeError as error:
            self.status.setText(str(error))
            return
        self.cards["ltp"].set_value(f"{symbol} subscribing…")
        self.cards["trend"].set_value("Connecting live feed…")
        self.cards["support"].set_value("Waiting for candles")
        self.cards["resistance"].set_value("Waiting for candles")
        self.cards["breakout"].set_value("Selected-TF close + volume")
        self.cards["breakdown"].set_value("Selected-TF close + volume")
        Thread(target=self.load_market_structure, args=(symbol, exchange_type, token, request_id), daemon=True).start()
        self.load_selected_timeframe()

    def capture_scheduled_snapshot(self):
        """Record once per completed five-minute bucket while the cash market is open."""
        if not LiveSession.connected() or not self.selected_symbol:
            return
        now = datetime.now()
        if market_session(now)["state"] != "OPEN":
            return
        if now.minute % 5:
            return
        bucket = now.strftime("%Y-%m-%d %H:%M")
        if bucket == self.last_snapshot_bucket:
            return
        self.last_snapshot_bucket = bucket
        timeframes = ("5m", "15m") if now.minute % 15 == 0 else ("5m",)
        self.capture_market_snapshot(timeframes)

    def capture_market_snapshot(self, timeframes=("5m", "15m")):
        # QPushButton.clicked emits a bool.  Keep this callable safe if it is
        # ever connected directly again, rather than iterating over True/False
        # inside the recorder thread.
        if isinstance(timeframes, bool):
            timeframes = ("5m", "15m")
        if not LiveSession.connected() or not self.selected_symbol:
            self.snapshot_status.setText("Snapshot recorder: select a live symbol after the broker connects.")
            return
        symbol = self.selected_symbol[0]
        self.snapshot_status.setText(f"Snapshot recorder: saving {symbol} 5m / 15m + focused option-chain data…")
        Thread(target=self._capture_market_snapshot, args=(symbol, timeframes), daemon=True).start()

    def _capture_market_snapshot(self, symbol, timeframes):
        try:
            count = MarketSnapshotRecorder(LiveSession.client).capture(symbol, timeframes)
            database = Database()
            try:
                alerts = database.evaluate_open_trade_alerts(symbol)
            finally:
                database.close()
            for alert in alerts:
                self.guard_alert.emit(alert)
            self.snapshot_saved.emit(f"Snapshot recorder: saved {count} new {symbol} record(s).")
        except (RuntimeError, ValueError, TypeError) as error:
            self.snapshot_error.emit(f"Snapshot recorder: {error}")

    def show_snapshot_saved(self, message):
        self.snapshot_status.setText(message)

    def show_snapshot_error(self, message):
        self.snapshot_status.setText(message)

    def show_guard_alert(self, alert):
        self.snapshot_status.setText(f"Open Trade Guard: {alert['title']}")
        QMessageBox.warning(self, "Open Trade Guard — review required", alert["message"])

    def load_selected_timeframe(self):
        if not LiveSession.connected() or not self.selected_symbol:
            return
        if self.timeframe.currentText() == "All timeframes":
            self.load_multi_timeframe()
            return
        symbol, exchange_type, token = self.selected_symbol
        request_id = self.selection_request
        self.multi_timeframe_detail.setText(f"Loading {symbol} {self.timeframe.currentText()} chart analysis...")
        Thread(target=self._load_single_timeframe, args=(symbol, exchange_type, token, self.timeframe.currentText(), request_id), daemon=True).start()

    def _load_single_timeframe(self, symbol, exchange_type, token, label, request_id):
        exchange = "BSE" if exchange_type == 3 else "NSE"
        requests = {"5m": ("FIVE_MINUTE", 5), "15m": ("FIFTEEN_MINUTE", 15), "1h": ("ONE_HOUR", 60), "1D": ("ONE_DAY", 365)}
        try:
            interval, days = requests[label]
            result = analyze_candles(LiveSession.client.get_recent_candles(exchange, token, interval, days))
            result.update({"symbol": symbol, "timeframe": label, "request_id": request_id})
            if request_id != self.selection_request:
                return
            self.structure_received.emit(result)
        except (RuntimeError, ValueError) as error:
            if request_id == self.selection_request:
                self.multi_timeframe_error.emit(str(error))

    def load_market_structure(self, symbol, exchange_type, token, request_id=None):
        request_id = self.selection_request if request_id is None else request_id
        exchange = "BSE" if exchange_type == 3 else "NSE"
        try:
            candles = LiveSession.client.get_recent_candles(exchange, token)
            result = analyze_candles(candles)
            result.update({"symbol": symbol, "timeframe": "5m", "request_id": request_id})
        except (RuntimeError, ValueError) as error:
            if request_id == self.selection_request:
                self.structure_error.emit({"symbol": symbol, "request_id": request_id, "message": str(error)})
            return
        if request_id != self.selection_request:
            return
        self.structure_received.emit(result)

    def show_structure(self, result):
        if not self.selected_symbol or result.get("symbol") != self.selected_symbol[0]:
            return
        if result.get("request_id", self.selection_request) != self.selection_request:
            return
        result = self._stabilize_structure(result)
        timeframe = result.get("timeframe", "5m")
        self.cards["trend"].set_value(result["state"])
        support_zone = result.get("support_zone") or {"low": result["support"], "high": result["support"]}
        resistance_zone = result.get("resistance_zone") or {"low": result["resistance"], "high": result["resistance"]}
        self.cards["support"].set_value(f"{support_zone['low']:,.2f} – {support_zone['high']:,.2f}")
        self.cards["resistance"].set_value(f"{resistance_zone['low']:,.2f} – {resistance_zone['high']:,.2f}")
        self.cards["breakout"].set_value(
            f"{timeframe} close > {result['breakout_level']:,.2f}\n{result['volume_condition']}"
        )
        self.cards["breakdown"].set_value(
            f"{timeframe} close < {result['breakdown_level']:,.2f}\n{result['volume_condition']}"
        )
        broker = broker_definition(LiveSession.broker_id or "angel_one").name
        self.status.setText(f"{broker}: {result['symbol']} {timeframe} levels refreshed from {result['candle_count']} candles")
        if result.get("timeframe"):
            self.multi_timeframe_detail.setText(
                f"{result['symbol']} {result['timeframe']} analysis: {result['state']}. "
                f"Support zone {support_zone['low']:,.2f}–{support_zone['high']:,.2f} | "
                f"Resistance zone {resistance_zone['low']:,.2f}–{resistance_zone['high']:,.2f}."
            )
        if timeframe == "5m":
            self.current_levels = {
                "symbol": result["symbol"], "support": result["support"],
                "resistance": result["resistance"],
            }
            self._check_level_proximity(result.get("price"))

    def _stabilize_structure(self, result):
        """Keep a valid clustered zone until a replacement repeats three times."""
        key = (result.get("symbol"), result.get("timeframe", "5m"))
        previous = self.structure_cache.get(key)
        if previous is None:
            self.structure_cache[key] = dict(result)
            return result
        tolerance = max(float(result.get("zone_tolerance", 0) or 0), 0.05)
        signature = (
            round(float(result["support"]) / tolerance),
            round(float(result["resistance"]) / tolerance),
        )
        pending_signature, count = self.pending_level_candidates.get(key, (None, 0))
        count = count + 1 if pending_signature == signature else 1
        self.pending_level_candidates[key] = (signature, count)
        price = float(result.get("price", 0) or 0)
        old_support = previous.get("support_zone") or {"low": previous["support"]}
        old_resistance = previous.get("resistance_zone") or {"high": previous["resistance"]}
        invalidated = price < float(old_support["low"]) - tolerance or price > float(old_resistance["high"]) + tolerance
        if count >= 3 or invalidated:
            self.structure_cache[key] = dict(result)
            self.pending_level_candidates.pop(key, None)
            return result
        stable = dict(result)
        for name in ("support", "resistance", "support_zone", "resistance_zone", "breakout_level", "breakdown_level"):
            if name in previous:
                stable[name] = previous[name]
        stable["levels_stabilized"] = True
        return stable

    def show_structure_error(self, payload):
        if payload.get("request_id") != self.selection_request or not self.selected_symbol or payload.get("symbol") != self.selected_symbol[0]:
            return
        message = payload.get("message", "Unknown candle error")
        self.cards["trend"].set_value("Structure unavailable")
        self.cards["support"].set_value("No reliable level")
        self.cards["resistance"].set_value("No reliable level")
        broker = broker_definition(LiveSession.broker_id or "angel_one").name
        self.status.setText(f"{broker}: live price connected; candle levels unavailable ({message})")

    def load_multi_timeframe(self):
        if not LiveSession.connected() or not self.selected_symbol:
            self.multi_timeframe_detail.setText("Select NIFTY, BANKNIFTY, or SENSEX after the broker connects first.")
            return
        symbol, exchange_type, token = self.selected_symbol
        request_id = self.selection_request
        self.multi_timeframe_detail.setText(f"Loading {symbol} 5m, 15m, 1h and 1D chart history…")
        Thread(target=self._load_multi_timeframe, args=(symbol, exchange_type, token, request_id), daemon=True).start()

    def _load_multi_timeframe(self, symbol, exchange_type, token, request_id):
        exchange = "BSE" if exchange_type == 3 else "NSE"
        requests = {"5m": ("FIVE_MINUTE", 5), "15m": ("FIFTEEN_MINUTE", 15), "1h": ("ONE_HOUR", 60), "1D": ("ONE_DAY", 365)}
        try:
            candles = {
                label: LiveSession.client.get_recent_candles(exchange, token, interval, days)
                for label, (interval, days) in requests.items()
            }
            result = analyze_multi_timeframe(candles)
            result["symbol"] = symbol
            result["request_id"] = request_id
        except (RuntimeError, ValueError) as error:
            if request_id == self.selection_request:
                self.multi_timeframe_error.emit(str(error))
            return
        if request_id != self.selection_request:
            return
        self.multi_timeframe_received.emit(result)

    def show_multi_timeframe(self, result):
        if not self.selected_symbol or result.get("symbol") != self.selected_symbol[0] or result.get("request_id") != self.selection_request:
            return
        patterns = " | ".join(f"{name}: {data['state'].replace(' structure', '')}, {data['pattern']}" for name, data in result["timeframes"].items())
        short_state = result["context"].replace(" multi-timeframe alignment", "").replace(" multi-timeframe structure — wait for confirmation", " / Wait")
        self.cards["trend"].set_value(f"{short_state}\nAlignment: {result['alignment_score']}/100")
        self.cards["support"].set_value(f"{result['support']:,.2f}")
        self.cards["resistance"].set_value(f"{result['resistance']:,.2f}")
        self.cards["breakout"].set_value("Select 5m / 15m\nfor entry confirmation")
        self.cards["breakdown"].set_value("Select 5m / 15m\nfor entry confirmation")
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
            else:
                service = OptionContractService()
            request = {"NSE": ["99926000", "99926009"], "BSE": ["99919000"]}
            for future in futures.values():
                request.setdefault(future["exchange"], []).append(future["token"])
            vix_instrument = self.vix_instrument
            if not vix_instrument:
                try:
                    vix_instrument = service.get_india_vix_instrument()
                except RuntimeError:
                    vix_instrument = None
            if vix_instrument:
                request.setdefault(vix_instrument["exchange"], []).append(vix_instrument["token"])
            quotes = LiveSession.client.get_market_quotes(request)
            vix_history = self.vix_history
            if vix_instrument and not vix_history:
                try:
                    vix_history = LiveSession.client.get_recent_candles(
                        vix_instrument["exchange"], vix_instrument["token"], "ONE_DAY", 365
                    )
                except (RuntimeError, ValueError, TypeError):
                    vix_history = []
            self.overview_received.emit({
                "quotes": {str(quote.get("symbolToken", quote.get("symboltoken", ""))): quote for quote in quotes},
                "futures": futures, "vix_instrument": vix_instrument, "vix_history": vix_history,
            })
        except RuntimeError as error:
            self.overview_error.emit(str(error))

    def show_overview(self, result):
        quotes, self.future_contracts = result["quotes"], result["futures"]
        self.vix_instrument = result.get("vix_instrument")
        self.vix_history = result.get("vix_history") or self.vix_history
        token_map = {"99926000": "NIFTY", "99926009": "BANKNIFTY", "99919000": "SENSEX"}
        spot_summaries = {}
        for token, symbol in token_map.items():
            quote = quotes.get(token)
            if not quote:
                spot_summaries[symbol] = "Spot quote unavailable"
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
            spot_summaries[symbol] = f"Spot  {price:,.2f}  |  {bias} ({percent_change:+.2f}%)"
        for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
            future = self.future_contracts.get(symbol)
            future_summary = "Future contract unavailable"
            if not future:
                self.overview_cards[symbol].set_value(
                    f"{spot_summaries.get(symbol, 'Spot quote unavailable')}\n{future_summary}"
                )
                continue
            quote = quotes.get(future["token"])
            if quote:
                future_summary = (
                    f"Future  {float(quote.get('ltp', 0) or 0):,.2f}"
                    f"  |  Expiry {future['expiry'].strftime('%d %b')}"
                )
            self.overview_cards[symbol].set_value(
                f"{spot_summaries.get(symbol, 'Spot quote unavailable')}\n{future_summary}"
            )
        vix_quote = quotes.get(str((self.vix_instrument or {}).get("token", "")))
        if vix_quote:
            vix = float(vix_quote.get("ltp", 0) or 0)
            context = classify_vix_percentile(vix, self.vix_history)
            percentile = f"P{context['percentile']:.0f}" if context.get("percentile") is not None else "fallback"
            self.overview_cards["INDIA VIX"].set_value(
                f"{vix:.2f}  |  {context['label']} ({percentile})\nUpdated {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            self.overview_cards["INDIA VIX"].set_value("Live VIX quote unavailable")
        self.overview_loading = False

    def show_overview_error(self, _message):
        self.overview_loading = False
        for card in self.overview_cards.values():
            card.set_value("Overview temporarily unavailable")

    def show_status(self, status):
        broker = broker_definition(LiveSession.broker_id or "angel_one").name
        self.status.setText(f"{broker}: {status}")

    def show_tick(self, tick):
        if not self.selected_symbol:
            return
        tick_token = tick.get("token") or tick.get("symbol_token") or tick.get("symbolToken")
        if tick_token is not None and str(tick_token) != str(self.selected_symbol[2]):
            return
        value = tick.get("last_traded_price") or tick.get("ltp") or tick.get("last_traded_price")
        if value is None:
            return
        price = float(value) / 100 if float(value) > 100000 else float(value)
        self.cards["ltp"].set_value(f"{price:,.2f}")
        self._check_level_proximity(price)

    def _check_level_proximity(self, price):
        if price is None or not self.current_levels:
            return
        result = classify_level_proximity(
            price, self.current_levels["support"], self.current_levels["resistance"]
        )
        state = result["state"]
        if state == self.last_level_state:
            return
        self.last_level_state = state
        if state not in {"SUPPORT_ZONE", "RESISTANCE_ZONE", "BELOW_SUPPORT", "ABOVE_RESISTANCE"}:
            return
        symbol = self.current_levels["symbol"]
        level_name = "support" if state in {"SUPPORT_ZONE", "BELOW_SUPPORT"} else "resistance"
        action = {
            "SUPPORT_ZONE": "has entered the marked support zone",
            "RESISTANCE_ZONE": "has entered the marked resistance zone",
            "BELOW_SUPPORT": "is below the marked support zone",
            "ABOVE_RESISTANCE": "is above the marked resistance zone",
        }[state]
        self.level_alert.emit({
            # One support and one resistance event per symbol/day. The level
            # may move slightly after every candle; that must not create a
            # fresh popup flood for the same logical market event.
            "dedupe_key": f"{symbol}:{level_name}",
            "title": f"TPS {level_name} alert — {symbol}",
            "message": (
                f"{symbol} {action}. Price {float(price):,.2f}; {level_name} "
                f"{result['level']:,.2f}. Review candle close, volume and market structure before acting."
            ),
        })
