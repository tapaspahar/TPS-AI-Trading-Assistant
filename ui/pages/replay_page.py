from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from engine.live_setup_capture import TIMEFRAMES, build_live_capture
from engine.market_structure import analyze_candles
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService


class ReplayPage(QWidget):
    """Candle-by-candle historical review using one downloaded Angel One dataset."""
    loaded = Signal(dict)
    load_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.candles = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Candle Replay â€” review past market behaviour without placing an order"))
        note = QLabel("Load historical future candles once, then move candle by candle. Values shown are calculated only from candles available up to that moment (no future-candle look-ahead).")
        note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout()
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.timeframe = QComboBox(); self.timeframe.addItems(("5m", "15m", "1h", "1D"))
        self.days = QComboBox(); self.days.addItems(("5", "15", "30"))
        form.addRow("Underlying", self.symbol); form.addRow("Timeframe", self.timeframe); form.addRow("History days", self.days)
        layout.addLayout(form)
        self.load_button = QPushButton("Load Candle Replay")
        self.load_button.clicked.connect(self.load_replay); layout.addWidget(self.load_button)
        self.slider = QSlider(); self.slider.setOrientation(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.Horizontal)
        self.slider.valueChanged.connect(self.show_candle); self.slider.setEnabled(False); layout.addWidget(self.slider)
        self.summary = QLabel("Connect Angel One and load a replay dataset."); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.loaded.connect(self.show_loaded); self.load_error.connect(self.show_error)

    def load_replay(self):
        if not LiveSession.connected():
            self.summary.setText("Connect Angel One from Settings first."); return
        self.load_button.setEnabled(False); self.summary.setText("Downloading one historical candle dataset…")
        Thread(target=self._load, args=(self.symbol.currentText(), self.timeframe.currentText(), int(self.days.currentText())), daemon=True).start()

    def _load(self, symbol, timeframe, days):
        try:
            future = OptionContractService().get_front_month_future(symbol)
            candles = LiveSession.client.get_recent_candles(future["exchange"], future["token"], TIMEFRAMES[timeframe][0], days)
            if len(candles) < 55: raise ValueError("Not enough candles returned for a reliable replay.")
            self.loaded.emit({"symbol": symbol, "timeframe": timeframe, "future": future["symbol"], "candles": candles})
        except (RuntimeError, ValueError) as error:
            self.load_error.emit(str(error))

    def show_loaded(self, result):
        self.load_button.setEnabled(True); self.candles = result["candles"]
        self.replay_symbol, self.replay_timeframe, self.future = result["symbol"], result["timeframe"], result["future"]
        self.slider.blockSignals(True); self.slider.setRange(50, len(self.candles) - 1); self.slider.setValue(50); self.slider.blockSignals(False)
        self.slider.setEnabled(True); self.show_candle(50)

    def show_candle(self, index):
        if not self.candles: return
        history = self.candles[:index + 1]
        try:
            capture = build_live_capture(self.replay_symbol, self.replay_timeframe, history, "Angel One historical future data")
            structure = analyze_candles(history[-40:])
            candle = history[-1]
            self.summary.setText(
                f"Candle {index - 49}/{len(self.candles) - 50} | {candle.get('time')} | O/H/L/C: {capture['open']} / {capture['high']} / {capture['low']} / {capture['close']}\n"
                f"Structure: {structure['state']} | Support {structure['support']:.2f} | Resistance {structure['resistance']:.2f}\n"
                f"RSI 14: {capture['rsi_14']} | ATR 14: {capture['atr_14']} | {capture['volume_signal']}. This is a study tool, not a trade instruction."
            )
        except ValueError as error: self.summary.setText(str(error))

    def show_error(self, message):
        self.load_button.setEnabled(True); self.summary.setText(f"Replay unavailable: {message}")
