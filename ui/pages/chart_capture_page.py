from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from services.chart_capture_service import ChartCaptureService, OCRUnavailableError
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService
from engine.live_setup_capture import INSTRUMENTS, TIMEFRAMES, build_live_capture


class ChartCapturePage(QWidget):
    symbol_ready = Signal(str)
    analysis_ready = Signal(dict)
    live_capture_received = Signal(dict)
    live_capture_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.service = ChartCaptureService()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Quick Chart Capture"))
        layout.addWidget(QLabel("Fixed profile: EMA 5 Pink | EMA 20 Violet | EMA 50 White | VWAP Yellow | SuperTrend Green/Red | Volume EMA 20"))
        layout.addWidget(QLabel("Select a broker/chart screenshot. OCR runs locally; verify every extracted value before trading."))
        choose = QPushButton("Choose Chart Screenshot")
        choose.clicked.connect(self.choose_screenshot)
        layout.addWidget(choose)
        layout.addWidget(QLabel("Live mode uses the nearest-expiry index future for traded Volume/VWAP; option-chain OI remains a separate confirmation."))
        self.live_capture_button = QPushButton("Capture Setup from Current-Month Future")
        self.live_capture_button.clicked.connect(self.capture_live_setup)
        layout.addWidget(self.live_capture_button)
        form = QFormLayout()
        self.fields = {}
        for key, label in (("symbol", "Symbol"), ("timeframe", "Timeframe"), ("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"), ("ema_5", "EMA 5 (Pink)"), ("ema_20", "EMA 20 (Violet)"), ("ema_50", "EMA 50 (White)"), ("vwap", "VWAP (Yellow)"), ("rsi_14", "RSI 14"), ("atr_14", "ATR 14"), ("supertrend", "SuperTrend"), ("supertrend_state", "SuperTrend State"), ("volume", "Volume"), ("volume_ema", "Volume EMA 20 (Value)")):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        copy_symbol = QPushButton("Use Verified Symbol in Journal")
        copy_symbol.clicked.connect(self.send_symbol)
        layout.addWidget(copy_symbol)
        self.raw_text = QPlainTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMinimumHeight(140)
        self.raw_text.setPlaceholderText("OCR text will appear here for review.")
        layout.addWidget(self.raw_text)
        layout.addStretch()
        self.live_capture_received.connect(self.apply_capture)
        self.live_capture_error.connect(self.show_live_capture_error)

    def choose_screenshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select chart screenshot", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            capture = self.service.read_image(path)
        except (OCRUnavailableError, OSError) as error:
            QMessageBox.warning(self, "Chart capture unavailable", str(error))
            return
        self.apply_capture(capture)
        # Verified values are evaluated directly for Options Workspace.

    def capture_live_setup(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Broker", "Connect live data from Settings first.")
            return
        symbol = self.fields["symbol"].text().strip().upper() or "NIFTY"
        timeframe = self.fields["timeframe"].text().strip() or "5m"
        if symbol not in INSTRUMENTS:
            QMessageBox.warning(self, "Live capture", "Live capture currently supports NIFTY, BANKNIFTY, and SENSEX.")
            return
        if timeframe not in TIMEFRAMES:
            QMessageBox.warning(self, "Live capture", "Use one of: 5m, 15m, 1h, 1D.")
            return
        self.live_capture_button.setEnabled(False)
        self.live_capture_button.setText("Capturing broker setup…")
        Thread(target=self._capture_live_setup, args=(symbol, timeframe), daemon=True).start()

    def _capture_live_setup(self, symbol, timeframe):
        interval, days = TIMEFRAMES[timeframe]
        try:
            future = OptionContractService().get_front_month_future(symbol)
            candles = LiveSession.client.get_recent_candles(future["exchange"], future["token"], interval, days)
            source = f"current-month future {future['symbol']} (expires {future['expiry'].strftime('%d %b %Y')})"
            self.live_capture_received.emit(build_live_capture(symbol, timeframe, candles, source))
        except (RuntimeError, ValueError) as error:
            self.live_capture_error.emit(str(error))

    def apply_capture(self, capture):
        for key, field in self.fields.items():
            field.setText(str(capture.get(key, "")))
        self.raw_text.setPlainText(capture.get("raw_text", ""))
        self.live_capture_button.setEnabled(True)
        self.live_capture_button.setText("Capture Setup from Current-Month Future")
        self.analysis_ready.emit(capture)

    def show_live_capture_error(self, message):
        self.live_capture_button.setEnabled(True)
        self.live_capture_button.setText("Capture Setup from Current-Month Future")
        QMessageBox.warning(self, "Live capture", message)

    def send_symbol(self):
        symbol = self.fields["symbol"].text().strip().upper()
        if not symbol:
            QMessageBox.information(self, "No symbol", "Scan a chart or enter a verified symbol first.")
            return
        self.symbol_ready.emit(symbol)
        QMessageBox.information(self, "Symbol copied", f"{symbol} was copied to the Trade Journal.")
