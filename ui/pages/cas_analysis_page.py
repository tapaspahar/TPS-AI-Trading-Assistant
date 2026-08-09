from threading import Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QGridLayout, QGroupBox, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.stock_derivative_service import StockDerivativeService
from ui.widgets.cards.dashboard_card import DashboardCard


class CasAnalysisPage(QWidget):
    universe_loaded = Signal(list)
    analysis_loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(10)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Closing Auction Session (CAS) Analysis"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Effective 03-08-2026 for cash-market securities with derivatives. TPS compares the 3:00-3:15 PM "
            "cash reference-window VWAP estimate with the final CAS close and the stock future close. It does not place orders."
        )
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.stock = QComboBox(); self.stock.setEditable(True); self.stock.setInsertPolicy(QComboBox.NoInsert)
        self.stock.setPlaceholderText("Load F&O stocks, then type a symbol")
        self.stock.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.stock.completer().setFilterMode(Qt.MatchContains)
        self.stock.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.load_button = QPushButton("Load CAS-Eligible F&O Stocks"); self.load_button.clicked.connect(self.load_universe)
        self.analyze_button = QPushButton("Analyze Latest Completed CAS"); self.analyze_button.clicked.connect(self.analyze)
        controls.addWidget(self.stock, 0, 0, 1, 2); controls.addWidget(self.load_button, 1, 0); controls.addWidget(self.analyze_button, 1, 1)
        layout.addLayout(controls)
        self.status = QLabel("Connect Angel One, load the F&O stock list, and select one CAS-eligible share.")
        self.status.setWordWrap(True); layout.addWidget(self.status)
        grid = QGridLayout()
        self.cards = {key: DashboardCard(title, "-") for key, title in (
            ("pressure", "CAS Closing Pressure"), ("reference", "3:00-3:15 Reference VWAP*"),
            ("close", "Final CAS Close"), ("impact", "Auction Impact"),
            ("future", "Stock Future Close"), ("basis", "Closing Futures Basis"),
        )}
        for index, card in enumerate(self.cards.values()):
            card.set_compact(True); grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        rules = QGroupBox("Official CAS timetable and data limits")
        rules_layout = QVBoxLayout(rules)
        self.detail = QLabel(
            "3:15-3:20 transition (no order entry) | 3:20-3:25 market + limit orders | "
            "3:25-random close between 3:28-3:30 limit orders only | Equity derivatives trade until 3:40.\n"
            "*TPS reference VWAP is a 5-minute OHLCV approximation. Exchange IEP and order imbalance are shown only if an API supplies them; TPS never guesses them.\n"
            "Rule source: SEBI circular dated 16-01-2026 and NSE CAS FAQ v2.0 (July 2026)."
        )
        self.detail.setWordWrap(True); rules_layout.addWidget(self.detail); layout.addWidget(rules)
        layout.addStretch()
        self.universe_loaded.connect(self.show_universe); self.analysis_loaded.connect(self.show_result); self.failed.connect(self.show_error)

    def load_universe(self):
        self.load_button.setEnabled(False); self.status.setText("Loading active NSE stock-option universe from Angel One...")
        Thread(target=self._load_universe, daemon=True).start()

    def _load_universe(self):
        try: self.universe_loaded.emit(StockDerivativeService(LiveSession.client).universe())
        except (RuntimeError, ValueError) as error: self.failed.emit(str(error))

    def show_universe(self, rows):
        self.stock.clear()
        for row in rows: self.stock.addItem(f"{row['underlying']} - {row['company']}", row)
        self.load_button.setEnabled(True); self.status.setText(f"Loaded {len(rows)} active stock-option shares; these are CAS eligible in the initial phase.")

    def analyze(self):
        equity = self.stock.currentData()
        if not equity: self.status.setText("Load and select a CAS-eligible F&O stock first."); return
        if not LiveSession.connected(): self.status.setText("Angel One is not connected. Connect it from Settings first."); return
        self.analyze_button.setEnabled(False); self.status.setText(f"Loading {equity['underlying']} cash and future closing candles...")
        Thread(target=self._analyze, args=(equity,), daemon=True).start()

    def _analyze(self, equity):
        try: self.analysis_loaded.emit(StockDerivativeService(LiveSession.client).analyze_cas(equity))
        except (RuntimeError, ValueError, KeyError, TypeError) as error: self.failed.emit(str(error))

    def show_result(self, result):
        self.cards["pressure"].set_value(f"{result['pressure']}\nConfidence {result['confidence']}%")
        self.cards["reference"].set_value(f"{result['cash_reference']:,.2f}")
        self.cards["close"].set_value(f"{result['cas_close']:,.2f}")
        self.cards["impact"].set_value(f"{result['impact_points']:+,.2f} ({result['impact_percent']:+.3f}%)\n{result['impact_atr']:+.2f} ATR")
        self.cards["future"].set_value(f"{result['future_close']:,.2f}\nMove {result['future_move']:+,.2f}")
        self.cards["basis"].set_value(f"{result['closing_basis']:+,.2f}\nFuture agreement {'YES' if result['future_agreement'] else 'NO'}")
        state = "Final session" if result["session_final"] else "Preview/incomplete session"
        self.status.setText(f"{result['underlying']} | {result['trade_date']} | {state} | Cash {result['cash_symbol']} | Future {result['future_symbol']}")
        self.detail.setText(
            f"Cash last candle: {result['cash_last_candle']} | Future last candle: {result['future_last_candle']}\n"
            f"{result['warning']}\nClosing pressure is evidence for review, not a guaranteed next-day prediction."
        )
        self.analyze_button.setEnabled(True)

    def show_error(self, message):
        self.load_button.setEnabled(True); self.analyze_button.setEnabled(True); self.status.setText(f"CAS analysis unavailable: {message}")
