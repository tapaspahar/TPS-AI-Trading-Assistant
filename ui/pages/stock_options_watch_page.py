from threading import Thread

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QGridLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.stock_option_watchlist_store import StockOptionWatchlistStore
from services.live_session import LiveSession
from services.stock_derivative_service import StockDerivativeService


class StockOptionsWatchPage(QWidget):
    universe_loaded = Signal(list)
    scan_loaded = Signal(list)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(10)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Stock Options Watch"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Watch up to 8 NSE stocks with active option contracts. Every scan uses completed 5-minute stock-future candles, "
            "EMA/VWAP/SuperTrend, volume, support/resistance and focused option-chain OI. PAPER CANDIDATE never places a broker order."
        )
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.stock = QComboBox(); self.stock.setEditable(True); self.stock.setInsertPolicy(QComboBox.NoInsert)
        self.stock.setPlaceholderText("Load F&O stocks, then type to search")
        self.stock.completer().setCaseSensitivity(Qt.CaseInsensitive); self.stock.completer().setFilterMode(Qt.MatchContains)
        self.stock.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.load_button = QPushButton("Load Active Stock-Option List"); self.load_button.clicked.connect(self.load_universe)
        self.add_button = QPushButton("Add to Watchlist"); self.add_button.clicked.connect(self.add_selected)
        self.remove_button = QPushButton("Remove Selected"); self.remove_button.clicked.connect(self.remove_selected)
        self.scan_button = QPushButton("Scan Watchlist Now"); self.scan_button.clicked.connect(self.scan)
        controls.addWidget(self.stock, 0, 0, 1, 4); controls.addWidget(self.load_button, 1, 0)
        controls.addWidget(self.add_button, 1, 1); controls.addWidget(self.remove_button, 1, 2); controls.addWidget(self.scan_button, 1, 3)
        layout.addLayout(controls)
        self.auto = QCheckBox("Auto scan after every 5-minute interval (research/paper candidates only)")
        self.auto.toggled.connect(self.toggle_auto); layout.addWidget(self.auto)
        self.status = QLabel("Load active F&O stocks and build a small watchlist. Angel One must remain connected.")
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels((
            "Stock", "State", "Side", "Score", "Entry timing", "Spot", "Contract",
            "Entry", "Stop loss", "Target", "Quantity", "Why / blockers",
        ))
        self.table.setMinimumHeight(360); self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
        self.detail = QLabel("No stock-option scan has run yet."); self.detail.setWordWrap(True); layout.addWidget(self.detail)
        layout.addStretch()
        self.store = StockOptionWatchlistStore(); self.universe = []; self.scanning = False
        self.timer = QTimer(self); self.timer.setInterval(300_000); self.timer.timeout.connect(self.scan)
        self.universe_loaded.connect(self.show_universe); self.scan_loaded.connect(self.show_results); self.failed.connect(self.show_error)
        self.refresh_table()

    def load_universe(self):
        self.load_button.setEnabled(False); self.status.setText("Loading active NSE stock-option universe...")
        Thread(target=self._load_universe, daemon=True).start()

    def _load_universe(self):
        try: self.universe_loaded.emit(StockDerivativeService(LiveSession.client).universe())
        except (RuntimeError, ValueError) as error: self.failed.emit(str(error))

    def show_universe(self, rows):
        self.universe = rows; self.stock.clear()
        for row in rows: self.stock.addItem(f"{row['underlying']} - {row['company']}", row)
        self.load_button.setEnabled(True); self.status.setText(f"Loaded {len(rows)} active F&O shares. Add up to 8 liquid stocks for automatic research scans.")

    def add_selected(self):
        equity = self.stock.currentData()
        if not equity: QMessageBox.information(self, "Stock Options Watch", "Load and select a stock first."); return
        try: self.store.save(equity)
        except ValueError as error: QMessageBox.warning(self, "Watchlist limit", str(error)); return
        self.refresh_table()

    def remove_selected(self):
        row = self.table.currentRow()
        if row < 0: return
        symbol = self.table.item(row, 0).data(Qt.UserRole)
        self.store.remove(symbol); self.refresh_table()

    def refresh_table(self):
        rows = self.store.load(); self.table.setRowCount(len(rows))
        for row_index, equity in enumerate(rows):
            item = QTableWidgetItem(equity["underlying"]); item.setData(Qt.UserRole, equity["underlying"])
            self.table.setItem(row_index, 0, item)
            for column in range(1, 12): self.table.setItem(row_index, column, QTableWidgetItem("Waiting" if column == 1 else "-"))

    def toggle_auto(self, enabled):
        if enabled:
            self.timer.start(); self.scan(); self.status.setText("Automatic 5-minute stock-option research scan enabled.")
        else:
            self.timer.stop(); self.status.setText("Automatic scan disabled. Manual Scan Watchlist Now remains available.")

    def scan(self):
        rows = self.store.load()
        if self.scanning or not rows: return
        if not LiveSession.connected(): self.status.setText("Angel One is not connected. Connect it from Settings first."); return
        self.scanning = True; self.scan_button.setEnabled(False); self.status.setText(f"Scanning {len(rows)} stock-option underlyings sequentially to respect API limits...")
        Thread(target=self._scan, args=(rows,), daemon=True).start()

    def _scan(self, rows):
        service = StockDerivativeService(LiveSession.client); results = []
        for equity in rows:
            try: results.append(service.analyze_option_setup(equity))
            except (RuntimeError, ValueError, KeyError, TypeError) as error:
                results.append({"underlying": equity["underlying"], "error": str(error)})
        self.scan_loaded.emit(results)

    def show_results(self, results):
        self.table.setRowCount(len(results)); candidates = []
        for row_index, result in enumerate(results):
            symbol = result["underlying"]
            first = QTableWidgetItem(symbol); first.setData(Qt.UserRole, symbol); self.table.setItem(row_index, 0, first)
            if result.get("error"):
                values = ("ERROR", "-", "-", "-", "-", "-", "-", "-", "-", "-", result["error"])
            else:
                plan = result.get("plan") or {}; quality = result.get("entry_quality") or {}
                blockers = result.get("blockers") or []
                reason = "All TPS checks passed; review paper candidate." if plan else "; ".join(blockers[:3]) or result["strategy"]["decision"]
                values = (
                    result["state"], result["candidate"], f"{result['score']}/100",
                    "TIMELY" if quality.get("timely") else "WAIT / EXTENDED", f"{result['spot']:,.2f}",
                    plan.get("contract", {}).get("symbol", "-"), f"{plan.get('entry', 0):,.2f}" if plan else "-",
                    f"{plan.get('stoploss', 0):,.2f}" if plan else "-", f"{plan.get('target', 0):,.2f}" if plan else "-",
                    str(plan.get("quantity", "-")) if plan else "-", reason,
                )
                if plan: candidates.append(f"{symbol} {result['candidate']} {plan['contract']['symbol']} @ {plan['entry']:.2f}")
            for column, value in enumerate(values, 1): self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents(); self.table.horizontalHeader().setStretchLastSection(True)
        self.detail.setText("Paper candidates: " + (" | ".join(candidates) if candidates else "None on this completed-candle scan."))
        self.status.setText(f"Scan complete: {len(results)} stocks checked | {len(candidates)} paper candidate(s). No broker order placed.")
        self.scanning = False; self.scan_button.setEnabled(True)

    def show_error(self, message):
        self.load_button.setEnabled(True); self.scan_button.setEnabled(True); self.scanning = False
        self.status.setText(f"Stock-option watch unavailable: {message}")
