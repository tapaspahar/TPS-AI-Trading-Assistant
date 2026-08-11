"""Selective live confluence workspace for the TPS Powerful Engine."""
from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.powerful_engine_service import PowerfulEngineService


class PowerfulEnginePage(QWidget):
    result_ready = Signal(dict)
    result_failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("TPS Powerful Engine"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Selective options signal controller: 5m/15m/1h structure, walk-forward Candle DNA purity, EMA/VWAP/SuperTrend, "
            "price action, directional volume, India VIX, OI zones aur ATM option liquidity agree hone par hi CE/PE signal publish hota hai. "
            "Conflict, missing data ya weak validation par engine WAIT karta hai."
        )
        note.setWordWrap(True); layout.addWidget(note)
        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX")); layout.addWidget(self.index)
        self.run = QPushButton("Run Powerful Engine on Completed Live Candles"); self.run.clicked.connect(self.analyze); layout.addWidget(self.run)
        self.status = QLabel("Read-only broker connect karke analysis run kijiye."); self.status.setWordWrap(True); layout.addWidget(self.status)
        grid = QGridLayout(); self.cards = {}
        for column, name in enumerate(("Final Decision", "CE Strength", "PE Strength", "Validated Purity")):
            box = QGroupBox(name); box_layout = QVBoxLayout(box); value = QLabel("-")
            value.setObjectName("metricValue"); value.setWordWrap(True); box_layout.addWidget(value)
            grid.addWidget(box, 0, column); self.cards[name] = value
        layout.addLayout(grid)
        self.evidence = self._section(layout, "Independent Evidence Ledger")
        self.blockers = self._section(layout, "Why Signal Was Published or Rejected")
        self.risk = self._section(layout, "Market, OI and Liquidity Context")
        self.research = self._section(layout, "Measurement Integrity")
        layout.addStretch()
        self.result_ready.connect(self.show_result); self.result_failed.connect(self.show_error)

    @staticmethod
    def _section(layout, title):
        box = QGroupBox(title); box_layout = QVBoxLayout(box); label = QLabel("Run engine to view evidence.")
        label.setWordWrap(True); box_layout.addWidget(label); layout.addWidget(box); return label

    def analyze(self):
        if not LiveSession.connected():
            self.status.setText("Settings me read-only broker connect kijiye."); return
        self.run.setEnabled(False); self.index.setEnabled(False)
        self.status.setText("Multiple timeframe candles, option chain, VIX aur historical purity analyze ho rahi hai...")
        Thread(target=self._worker, args=(self.index.currentText(),), daemon=True).start()

    def _worker(self, symbol):
        try:
            self.result_ready.emit(PowerfulEngineService(LiveSession.client).analyze(symbol))
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            self.result_failed.emit(str(error))

    def show_result(self, result):
        self.cards["Final Decision"].setText(result["signal"])
        self.cards["CE Strength"].setText(f"{result['ce_strength']:.1f}%")
        self.cards["PE Strength"].setText(f"{result['pe_strength']:.1f}%")
        self.cards["Validated Purity"].setText(
            f"{result['validated_pre_candle_purity']:.1f}%\n{result['validated_pre_candle_signals']} historical signals"
        )
        self.status.setText(
            f"{result['provider']} | {result['future_symbol']} | Completed candle {result['candle_time']} | "
            f"Spot {result['spot']:,.2f} | Expiry {result['expiry']}"
        )
        self.evidence.setText("\n".join(
            f"{'PASS' if item['side'] == result.get('candidate') and item['available'] else 'OPPOSE' if item['side'] not in ('NEUTRAL', result.get('candidate')) and item['available'] else 'WAIT'} "
            f"— {item['layer']} ({item['weight']:.0f}): {item['detail']}"
            for item in result["evidence"]
        ))
        blockers = result["blockers"]
        self.blockers.setText(
            "SIGNAL PUBLISHED — all hard gates cleared." if result["published"] else
            "ENGINE ABSTAINED:\n" + "\n".join("• " + item for item in blockers)
        )
        chain, environment = result["chain"], result["environment"]
        quote = result.get("option_quote") or {}
        spread = result.get("spread_percent")
        self.risk.setText(
            f"Regime: {result['regime']} | India VIX: {result['vix'] or 'unavailable'} ({result['vix_zone']})\n"
            f"OI PCR: {chain.get('pcr_oi')} | Put support: {chain.get('put_support')} | Call resistance: {chain.get('call_resistance')} | "
            f"Quoted contracts: {chain.get('quoted_contracts')}/{chain.get('total_contracts')}\n"
            f"ATM candidate: {quote.get('symbol', 'not selected')} | LTP {quote.get('ltp', '-')} | Bid/Ask {quote.get('bid', '-')} / {quote.get('ask', '-')} | "
            f"Spread {f'{spread:.2f}%' if spread is not None else 'unavailable'}\n"
            f"Expected daily range remaining: {environment.get('remaining_expected_range', 'unavailable')} points"
        )
        self.research.setText(
            "Historical prediction ratio sirf Candle DNA ke chronological walk-forward audit se aata hai. "
            "CE/PE Strength live evidence agreement hai—win probability nahi. Full Powerful Engine accuracy tabhi publish hogi "
            "jab sufficient forward-market signals aur outcomes database me collect ho jayenge.\n" + result["warning"]
        )
        self._unlock()

    def show_error(self, message):
        self.status.setText(f"Powerful Engine unavailable: {message}"); self._unlock()

    def _unlock(self):
        self.run.setEnabled(True); self.index.setEnabled(True)
