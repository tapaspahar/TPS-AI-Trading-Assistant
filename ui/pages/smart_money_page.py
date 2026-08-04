from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from engine.smart_money_engine import SmartMoneyEngine
from services.live_session import LiveSession
from services.smart_money_data_service import SmartMoneyDataService


class SmartMoneyPage(QWidget):
    analysis_loaded = Signal(dict)
    analysis_failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Smart Money & Price Action Lab"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Rule-based analysis of completed current-month index-future OHLCV candles. It detects price-action evidence; it does not see hidden orders, predict certainty, or place a trade.")
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.timeframe = QComboBox(); self.timeframe.addItems(("5m", "15m"))
        self.run = QPushButton("Analyze Live Price Action from Angel One"); self.run.clicked.connect(self.load)
        controls.addWidget(self.index, 0, 0); controls.addWidget(self.timeframe, 0, 1); controls.addWidget(self.run, 0, 2)
        layout.addLayout(controls)
        self.status = QLabel("Connect Angel One in Settings, then run a completed-candle analysis.")
        self.status.setWordWrap(True); layout.addWidget(self.status)
        cards = QGridLayout(); self.cards = {}
        for column, key in enumerate(("Direction", "Score / Grade", "Structure", "Latest Event")):
            box = QGroupBox(key); box_layout = QVBoxLayout(box); value = QLabel("-"); value.setWordWrap(True)
            value.setObjectName("metricValue"); box_layout.addWidget(value); cards.addWidget(box, 0, column); self.cards[key] = value
        layout.addLayout(cards)
        self.market = self._section(layout, "Liquidity, Structure and Traps")
        self.zones = self._section(layout, "ICT-style Context, FVG, Supply / Demand and Candle Volume Profile")
        self.patterns = self._section(layout, "Candle Patterns and Full Evidence")
        self.caution = self._section(layout, "Important Limits")
        layout.addStretch()
        self.analysis_loaded.connect(self.show_result); self.analysis_failed.connect(self.show_error)

    @staticmethod
    def _section(layout, title):
        box = QGroupBox(title); box_layout = QVBoxLayout(box); label = QLabel("Run analysis to view evidence.")
        label.setWordWrap(True); label.setTextInteractionFlags(label.textInteractionFlags()); box_layout.addWidget(label)
        layout.addWidget(box); return label

    def load(self):
        if not LiveSession.connected():
            self.status.setText("Angel One is not connected. Connect it from Settings first."); return
        self.run.setEnabled(False); self.index.setEnabled(False); self.timeframe.setEnabled(False)
        self.status.setText("Loading completed future candles and calculating transparent TPS rules...")
        Thread(target=self._worker, args=(self.index.currentText(), self.timeframe.currentText()), daemon=True).start()

    def _worker(self, symbol, timeframe):
        try:
            data = SmartMoneyDataService(LiveSession.client).load(symbol, timeframe)
            data["analysis"] = SmartMoneyEngine().analyze(data["candles"])
            data.pop("candles", None); self.analysis_loaded.emit(data)
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            self.analysis_failed.emit(str(error))

    @staticmethod
    def _zone(zone):
        return f"{zone['low']:,.2f} - {zone['high']:,.2f}"

    def show_result(self, data):
        result = data["analysis"]
        self.status.setText(f"Source: {data['source']} | Last completed candle: {data['candle_time']}")
        self.cards["Direction"].setText(result["direction"])
        self.cards["Score / Grade"].setText(f"{result['score']}/100 - {result['grade']}\nBull {result['bullish_score']} | Bear {result['bearish_score']}")
        self.cards["Structure"].setText(result["structure"])
        self.cards["Latest Event"].setText(result["event"] or "None")
        self.market.setText(
            f"Liquidity sweep: {result['liquidity_sweep']}\nBOS: {result['bos']} | CHOCH: {result['choch']}\n"
            f"Fake breakout: {result['fake_breakout']} | VWAP event: {result['vwap_event']}\n"
            f"Confirmed swing high/low: {result['swing_high']:,.2f} / {result['swing_low']:,.2f}\n"
            f"Volume: {result['volume_ratio']:.2f}x EMA20 | ATR: {result['atr']:,.2f}"
        )
        profile, fvg = result["volume_profile"], result["fvg"]
        order_block = result["order_block"]
        fvg_text = "None" if not fvg else f"{fvg['type']} {fvg['low']:,.2f} - {fvg['high']:,.2f}"
        self.zones.setText(
            f"Dealing-range location: {result['ict_location']} | Equilibrium: {result['equilibrium']:,.2f}\n"
            f"Demand zone: {self._zone(result['demand_zone'])} | Supply zone: {self._zone(result['supply_zone'])}\n"
            f"Latest FVG: {fvg_text}\n{order_block['type']}: {self._zone(order_block)}\n"
            f"Candle Volume Profile: POC {profile['poc']:,.2f} | "
            f"VAL {profile['value_area_low']:,.2f} | VAH {profile['value_area_high']:,.2f}\n{profile['method']}"
        )
        self.patterns.setText("Patterns: " + ", ".join(result["patterns"]) + "\n\n" + "\n".join("• " + item for item in result["evidence"]))
        self.caution.setText("\n".join("• " + item for item in result["warnings"]))
        self._unlock()

    def show_error(self, message):
        self.status.setText(f"Analysis failed: {message}"); self._unlock()

    def _unlock(self):
        self.run.setEnabled(True); self.index.setEnabled(True); self.timeframe.setEnabled(True)
