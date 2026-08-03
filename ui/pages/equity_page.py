from threading import Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from core.equity_watchlist_store import EquityWatchlistStore
from engine.equity_analysis import analyze_equity
from engine.live_setup_capture import TIMEFRAMES
from services.equity_service import EquityInstrumentService
from services.live_session import LiveSession
from ui.widgets.cards.dashboard_card import DashboardCard


class EquityPage(QWidget):
    """NSE cash-equity research page; planning only, never broker order execution."""
    instruments_loaded = Signal(list)
    analysis_ready = Signal(dict)
    load_error = Signal(str)
    download_progress = Signal(int, str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Equity Research Workspace - historical chart planning for NSE listed shares"))
        note = QLabel("Load the Angel One NSE equity list once, choose a share, then analyse historical candles. This is long-only decision support; it does not place orders or guarantee returns.")
        note.setWordWrap(True); layout.addWidget(note)

        form = QFormLayout()
        self.share = QComboBox(); self.share.setEditable(True); self.share.setInsertPolicy(QComboBox.NoInsert)
        self.share.setPlaceholderText("Load NSE shares, then type to search")
        self.timeframe = QComboBox(); self.timeframe.addItems(("1D", "1h", "15m", "5m"))
        self.days = QComboBox(); self.days.addItems(("90", "180", "365"))
        form.addRow("NSE share", self.share); form.addRow("Analysis timeframe", self.timeframe); form.addRow("History days", self.days)
        layout.addLayout(form)
        self.load_button = QPushButton("Load Listed NSE Shares"); self.load_button.clicked.connect(self.load_instruments); layout.addWidget(self.load_button)
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setValue(0)
        self.download_progress_bar.setTextVisible(True)
        self.download_progress_bar.setFormat("Ready to load share list")
        layout.addWidget(self.download_progress_bar)
        self.analyze_button = QPushButton("Analyze Selected Share"); self.analyze_button.clicked.connect(self.analyze_selected); layout.addWidget(self.analyze_button)
        self.company_detail = QLabel("Company details will appear here after selecting a share."); self.company_detail.setWordWrap(True); layout.addWidget(self.company_detail)

        layout.addWidget(QLabel("My Equity Watchlist"))
        watchlist_actions = QHBoxLayout()
        self.add_watchlist_button = QPushButton("Add Selected Share")
        self.remove_watchlist_button = QPushButton("Remove Watchlist Share")
        watchlist_actions.addWidget(self.add_watchlist_button); watchlist_actions.addWidget(self.remove_watchlist_button)
        layout.addLayout(watchlist_actions)
        self.watchlist = QListWidget()
        self.watchlist.setMinimumHeight(120)
        layout.addWidget(self.watchlist)

        grid = QGridLayout()
        self.cards = {key: DashboardCard(title, "Waiting") for key, title in (("price", "Last Candle Close"), ("state", "Chart Structure"), ("score", "Research Score"), ("support", "Support"), ("resistance", "Resistance"), ("entry", "Long Entry Trigger"), ("stop", "Protective Stop"), ("target1", "Target 1"), ("target2", "Target 2"))}
        for index, card in enumerate(self.cards.values()):
            card.set_compact(True); grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        self.summary = QLabel("Load a share list to begin equity research."); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        layout.addStretch()
        self.equities = []
        self.watchlist_store = EquityWatchlistStore()
        self.instruments_loaded.connect(self.show_instruments); self.analysis_ready.connect(self.show_analysis); self.load_error.connect(self.show_error)
        self.download_progress.connect(self.show_download_progress)
        self.share.currentIndexChanged.connect(self.show_selected_company)
        self.add_watchlist_button.clicked.connect(self.add_selected_to_watchlist)
        self.remove_watchlist_button.clicked.connect(self.remove_selected_from_watchlist)
        self.watchlist.itemDoubleClicked.connect(self.select_watchlist_equity)
        self.refresh_watchlist()

    def load_instruments(self):
        self.load_button.setEnabled(False); self.download_progress_bar.setRange(0, 100); self.download_progress_bar.setValue(0)
        self.download_progress_bar.setFormat("Starting download…"); self.summary.setText("Downloading today's Angel One NSE equity list…")
        Thread(target=self._load_instruments, daemon=True).start()

    def _load_instruments(self):
        try:
            self.instruments_loaded.emit(EquityInstrumentService().get_equities(self.download_progress.emit))
        except RuntimeError as error:
            self.load_error.emit(str(error))

    def show_instruments(self, equities):
        self.load_button.setEnabled(True); self.equities = equities; self.share.blockSignals(True); self.share.clear()
        for item in equities:
            self.share.addItem(f"{item['symbol']} - {item['company']}", item)
        self.share.blockSignals(False)
        self.summary.setText(f"Loaded {len(equities):,} NSE equity shares from Angel One. Type a symbol or company name to search.")
        self.download_progress_bar.setRange(0, 100); self.download_progress_bar.setValue(100)
        self.download_progress_bar.setFormat(f"Ready - {len(equities):,} NSE shares loaded")
        self.show_selected_company()

    def show_download_progress(self, percent, message):
        if percent < 0:
            self.download_progress_bar.setRange(0, 0)
        else:
            self.download_progress_bar.setRange(0, 100)
            self.download_progress_bar.setValue(percent)
        self.download_progress_bar.setFormat(message)
        self.summary.setText(message)

    def show_selected_company(self):
        item = self.share.currentData()
        if item:
            self.company_detail.setText(f"Company: {item['company']} | Trading symbol: {item['symbol']} | Exchange: NSE | Angel One token: {item['token']}")

    def analyze_selected(self):
        item = self.share.currentData()
        if not item:
            QMessageBox.information(self, "Equity research", "Load the NSE share list and select a share first."); return
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect read-only Angel One data from Settings before analysing share history."); return
        self.analyze_button.setEnabled(False); self.summary.setText("Downloading historical equity candles and calculating the research plan…")
        Thread(target=self._analyze, args=(item, self.timeframe.currentText(), int(self.days.currentText())), daemon=True).start()

    def _analyze(self, item, timeframe, days):
        try:
            candles = LiveSession.client.get_recent_candles(item["exchange"], item["token"], TIMEFRAMES[timeframe][0], days)
            result = analyze_equity(candles); result.update({"company": item["company"], "symbol": item["symbol"], "timeframe": timeframe, "days": days})
            self.analysis_ready.emit(result)
        except (RuntimeError, ValueError) as error:
            self.load_error.emit(str(error))

    def show_analysis(self, result):
        self.analyze_button.setEnabled(True)
        values = (("price", f"{result['price']:,.2f}"), ("state", result["state"]), ("score", f"{result['score']}/100"), ("support", f"{result['support']:,.2f}"), ("resistance", f"{result['resistance']:,.2f}"), ("entry", f"{result['entry']:,.2f}"), ("stop", f"{result['stop_loss']:,.2f}"), ("target1", f"{result['target_1']:,.2f}"), ("target2", f"{result['target_2']:,.2f}"))
        for key, value in values: self.cards[key].set_value(value)
        self.summary.setText(f"{result['company']} ({result['symbol']}) | {result['timeframe']} | {result['candle_count']} candles\nPlan: {result['plan_state']} | {result['plan_note']}\nRSI 14: {result['rsi_14']:.2f} | ATR 14: {result['atr_14']:.2f} | {result['volume_signal']}\nLevels are chart-based study levels, not a recommendation or guarantee.")
        self.watchlist_store.update_analysis(result["symbol"], result)
        self.refresh_watchlist()

    def add_selected_to_watchlist(self):
        item = self.share.currentData()
        if not item:
            QMessageBox.information(self, "Equity watchlist", "Load and select an NSE share first.")
            return
        self.watchlist_store.save_equity(item)
        self.refresh_watchlist()

    def remove_selected_from_watchlist(self):
        selected = self.watchlist.currentItem()
        if not selected:
            QMessageBox.information(self, "Equity watchlist", "Select a watchlist share to remove.")
            return
        self.watchlist_store.remove(selected.data(Qt.UserRole)["symbol"])
        self.refresh_watchlist()

    def refresh_watchlist(self):
        self.watchlist.clear()
        for equity in self.watchlist_store.load():
            detail = "Not analysed"
            if equity.get("last_price") is not None:
                detail = f"Last {float(equity['last_price']):,.2f} | Score {int(equity.get('score', 0))}/100 | {equity.get('plan_state', '')}"
            self.watchlist.addItem(f"{equity['symbol']} - {equity.get('company', '')} | {detail}")
            self.watchlist.item(self.watchlist.count() - 1).setData(Qt.UserRole, equity)

    def select_watchlist_equity(self, selected):
        equity = selected.data(Qt.UserRole)
        index = self.share.findData(equity)
        if index < 0:
            index = next((i for i in range(self.share.count()) if (self.share.itemData(i) or {}).get("symbol") == equity["symbol"]), -1)
        if index >= 0:
            self.share.setCurrentIndex(index)
        else:
            QMessageBox.information(self, "Equity watchlist", "Load today's NSE share list before opening this watchlist item.")

    def show_error(self, message):
        self.load_button.setEnabled(True); self.analyze_button.setEnabled(True); self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setFormat("Download unavailable")
        self.summary.setText(f"Equity analysis unavailable: {message}")
