from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from services.chart_capture_service import ChartCaptureService, OCRUnavailableError


class ChartCapturePage(QWidget):
    symbol_ready = Signal(str)
    analysis_ready = Signal(dict)

    def __init__(self):
        super().__init__()
        self.service = ChartCaptureService()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Quick Chart Capture"))
        layout.addWidget(QLabel("Fixed profile: EMA 5 Pink | EMA 20 Violet | EMA 50 White | VWAP Yellow | SuperTrend Green/Red | Volume EMA 20"))
        layout.addWidget(QLabel("Select a broker/chart screenshot. OCR runs locally; verify every extracted value before trading."))
        choose = QPushButton("Choose Chart Screenshot")
        choose.clicked.connect(self.choose_screenshot)
        layout.addWidget(choose)
        form = QFormLayout()
        self.fields = {}
        for key, label in (("symbol", "Symbol"), ("timeframe", "Timeframe"), ("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"), ("ema_5", "EMA 5 (Pink)"), ("ema_20", "EMA 20 (Violet)"), ("ema_50", "EMA 50 (White)"), ("vwap", "VWAP (Yellow)"), ("supertrend", "SuperTrend"), ("supertrend_state", "SuperTrend State"), ("volume", "Volume"), ("volume_ema_period", "Volume EMA")):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        copy_symbol = QPushButton("Use Verified Symbol in Journal")
        copy_symbol.clicked.connect(self.send_symbol)
        layout.addWidget(copy_symbol)
        self.raw_text = QPlainTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setPlaceholderText("OCR text will appear here for review.")
        layout.addWidget(self.raw_text)

    def choose_screenshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select chart screenshot", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            capture = self.service.read_image(path)
        except (OCRUnavailableError, OSError) as error:
            QMessageBox.warning(self, "Chart capture unavailable", str(error))
            return
        for key, field in self.fields.items():
            field.setText(capture[key])
        self.raw_text.setPlainText(capture["raw_text"])
        # Send every extracted value to Decision Engine V1 immediately. Fields
        # remain editable there because OCR can be uncertain.
        self.analysis_ready.emit(capture)

    def send_symbol(self):
        symbol = self.fields["symbol"].text().strip().upper()
        if not symbol:
            QMessageBox.information(self, "No symbol", "Scan a chart or enter a verified symbol first.")
            return
        self.symbol_ready.emit(symbol)
        QMessageBox.information(self, "Symbol copied", f"{symbol} was copied to the Trade Journal.")
