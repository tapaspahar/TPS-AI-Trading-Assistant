"""UI for the experimental, leakage-safe next-candle probability engine."""
from datetime import datetime, timedelta
from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QGroupBox, QLabel, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from engine.live_setup_capture import TIMEFRAMES
from engine.pre_candle_probability import analyze_pre_candle_probability
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService


class PreCandlePage(QWidget):
    result_ready = Signal(dict)
    result_failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)

        title = QLabel("Pre-Candle Probability Lab"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "TPS Candle DNA engine completed candles ke shape, wick/body, momentum, EMA regime, volatility, "
            "volume aur intraday timing ko historical analogs se compare karta hai. Signal tabhi dikhega jab "
            "expanding walk-forward test me selected purity gate clear ho. Ye prediction research hai, guarantee nahi."
        )
        note.setWordWrap(True); layout.addWidget(note)

        form = QFormLayout()
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.timeframe = QComboBox(); self.timeframe.addItems(("5m", "15m", "1h"))
        self.days = QComboBox(); self.days.addItems(("15", "30", "60")); self.days.setCurrentText("30")
        self.purity = QSpinBox(); self.purity.setRange(50, 95); self.purity.setValue(60); self.purity.setSuffix("%")
        form.addRow("Index", self.symbol); form.addRow("Prediction timeframe", self.timeframe)
        form.addRow("Historical training days", self.days); form.addRow("Minimum validated purity", self.purity)
        layout.addLayout(form)
        self.run = QPushButton("Calculate Next-Candle Probability")
        self.run.clicked.connect(self.calculate); layout.addWidget(self.run)
        self.status = QLabel("Broker connect karke completed-candle probability calculate kijiye.")
        self.status.setWordWrap(True); layout.addWidget(self.status)

        cards = QGridLayout(); self.cards = {}
        for column, name in enumerate(("Published Signal", "Bullish", "Bearish", "Range")):
            box = QGroupBox(name); box_layout = QVBoxLayout(box)
            value = QLabel("-"); value.setObjectName("metricValue"); value.setWordWrap(True)
            box_layout.addWidget(value); cards.addWidget(box, 0, column); self.cards[name] = value
        layout.addLayout(cards)
        self.validation = self._section(layout, "Walk-Forward Purity Audit")
        self.analogs = self._section(layout, "Candle DNA Evidence")
        self.limit = self._section(layout, "Use Limit")
        layout.addStretch()
        self.result_ready.connect(self.show_result); self.result_failed.connect(self.show_error)

    @staticmethod
    def _section(layout, title):
        box = QGroupBox(title); box_layout = QVBoxLayout(box)
        label = QLabel("Run analysis to view evidence."); label.setWordWrap(True)
        box_layout.addWidget(label); layout.addWidget(box); return label

    def calculate(self):
        if not LiveSession.connected():
            self.status.setText("Settings me read-only broker connect kijiye."); return
        self._lock(True)
        self.status.setText("Completed candles download karke leakage-safe walk-forward validation chal rahi hai...")
        args = (self.symbol.currentText(), self.timeframe.currentText(), int(self.days.currentText()), self.purity.value())
        Thread(target=self._worker, args=args, daemon=True).start()

    @staticmethod
    def _completed(candles, minutes):
        rows = list(candles)
        if not rows:
            return rows
        try:
            last = datetime.fromisoformat(str(rows[-1]["time"]))
            now = datetime.now(last.tzinfo) if last.tzinfo else datetime.now()
            if last + timedelta(minutes=minutes) > now:
                rows.pop()
        except (KeyError, TypeError, ValueError):
            pass
        return rows

    def _worker(self, symbol, timeframe, days, purity):
        try:
            future = OptionContractService().get_front_month_future(symbol)
            interval, minutes = TIMEFRAMES[timeframe]
            candles = LiveSession.client.get_recent_candles(future["exchange"], future["token"], interval, days)
            completed = self._completed(candles, minutes)
            result = analyze_pre_candle_probability(completed, purity)
            result.update({
                "symbol": symbol, "timeframe": timeframe, "future_symbol": future["symbol"],
                "source": getattr(LiveSession.client, "provider_name", "Broker"),
                "candle_count": len(completed),
            })
            self.result_ready.emit(result)
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            self.result_failed.emit(str(error))

    def show_result(self, result):
        self.cards["Published Signal"].setText(result["signal"])
        self.cards["Bullish"].setText(f"{result['bullish_probability']:.1f}%")
        self.cards["Bearish"].setText(f"{result['bearish_probability']:.1f}%")
        self.cards["Range"].setText(f"{result['range_probability']:.1f}%")
        expected = result["expected_move_points"]
        expected_text = f"{expected:+.2f} points ({result['expected_move_atr']:+.2f} ATR)"
        self.status.setText(
            f"{result['source']} | {result['future_symbol']} {result['timeframe']} | "
            f"Last completed candle: {result['last_candle_time']} | Close {result['last_close']:,.2f}"
        )
        self.validation.setText(
            f"Configured gate: {result['minimum_purity']}%\n"
            f"Walk-forward purity: {result['validated_purity']:.1f}% "
            f"({result['validation_correct']}/{result['validation_signals']} eligible historical signals correct)\n"
            f"Current top probability: {result['confidence']:.1f}% | Published: {'YES' if result['published'] else 'NO'}\n"
            "Purity calculation me har prediction ko sirf us waqt available purani candles mili; next candle pehle se nahi dikhayi gayi."
        )
        self.analogs.setText(
            f"Method: {result['method']}\n"
            f"Historical analog library: {result['historical_analogs']} | Nearest analog vote: {result['nearest_analogs']}\n"
            f"Average analog distance: {result['analog_distance']:.3f} | ATR: {result['atr']:.2f}\n"
            f"Analog-weighted next close movement: {expected_text}\n"
            "Prediction candle banne se pehle latest completed candle tak ke data par freeze ki gayi hai."
        )
        self.limit.setText(
            result["warning"] + "\n60% gate ka matlab ye nahi ki har 10 predictions me exactly 6 correct hongi. "
            "Broker data, regime change, slippage aur option premium behaviour alag ho sakte hain; paper validation ke bina manual trade na lein."
        )
        self._lock(False)

    def show_error(self, message):
        self.status.setText(f"Pre-candle analysis unavailable: {message}")
        self._lock(False)

    def _lock(self, locked):
        for widget in (self.run, self.symbol, self.timeframe, self.days, self.purity):
            widget.setEnabled(not locked)
