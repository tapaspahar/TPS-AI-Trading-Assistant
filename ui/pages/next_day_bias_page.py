from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from engine.next_day_bias_engine import NextDayBiasEngine
from services.chart_capture_service import ChartCaptureService, OCRUnavailableError


class NextDayBiasPage(QWidget):
    """Verified closing-evidence workspace for three supported indices."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Next-Day Bias Lab"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Upload closing Spot, current-month Future and nearest-expiry Option Chain snapshots. OCR is only an assistant—verify every field before calculating a probabilistic next-session bias.")
        note.setWordWrap(True); layout.addWidget(note)

        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX")); layout.addWidget(self.index)
        uploads = QGridLayout(); self.upload_labels = {}
        for column, (key, label) in enumerate((("spot", "1. Spot Chart"), ("future", "2. Future Chart"), ("chain", "3. Option Chain"))):
            button = QPushButton(f"Upload {label}"); button.clicked.connect(lambda _=False, kind=key: self._upload(kind))
            status = QLabel("Not selected"); status.setWordWrap(True); self.upload_labels[key] = status
            uploads.addWidget(button, 0, column); uploads.addWidget(status, 1, column)
        layout.addLayout(uploads)

        charts = QGridLayout()
        self.fields = {}
        for column, (prefix, heading) in enumerate((("spot", "Verified Spot close"), ("future", "Verified Future close"))):
            box = QGroupBox(heading); form = QFormLayout(box)
            for key, label in (("close", "Close"), ("ema5", "EMA 5"), ("ema20", "EMA 20"),
                               ("ema50", "EMA 50"), ("vwap", "VWAP"), ("supertrend", "SuperTrend")):
                field = QLineEdit(); self.fields[f"{prefix}_{key}"] = field; form.addRow(label, field)
            charts.addWidget(box, 0, column)
        layout.addLayout(charts)

        chain = QGroupBox("Verified Option Chain and range inputs"); form = QFormLayout(chain)
        for key, label, default in (("put_support", "Maximum Put-OI support", ""),
                                    ("call_resistance", "Maximum Call-OI resistance", ""),
                                    ("oi_pcr", "OI PCR", "1.00"), ("atm_call", "ATM Call premium", "0"),
                                    ("atm_put", "ATM Put premium", "0"), ("atr", "Spot ATR 14", "0")):
            field = QLineEdit(default); self.fields[key] = field; form.addRow(label, field)
        layout.addWidget(chain)
        self.verify = QComboBox(); self.verify.addItems(("Not verified", "I verified all closing values")); layout.addWidget(self.verify)
        run = QPushButton("Calculate Next-Day Bias"); run.clicked.connect(self.calculate); layout.addWidget(run)
        self.result = QLabel("No forecast calculated. Closing evidence is observational and cannot include overnight news or gap risk.")
        self.result.setWordWrap(True); self.result.setTextInteractionFlags(self.result.textInteractionFlags()); layout.addWidget(self.result)
        layout.addStretch()

    def _upload(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, "Select closing snapshot", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path: return
        self.upload_labels[kind].setText(path.split("/")[-1].split("\\")[-1])
        if kind == "chain":
            self.upload_labels[kind].setText(self.upload_labels[kind].text() + " — selected; enter max-OI/PCR values below")
            return
        try:
            data = ChartCaptureService().read_image(path)
            for source, target in (("close", "close"), ("ema_5", "ema5"), ("ema_20", "ema20"),
                                   ("ema_50", "ema50"), ("vwap", "vwap"), ("supertrend", "supertrend")):
                if data.get(source): self.fields[f"{kind}_{target}"].setText(str(data[source]))
            self.upload_labels[kind].setText(self.upload_labels[kind].text() + " — OCR loaded; verify fields")
        except (OCRUnavailableError, OSError) as error:
            self.upload_labels[kind].setText(f"Selected; OCR unavailable: {error}")

    def calculate(self):
        if self.verify.currentIndex() != 1:
            self.result.setText("BLOCKED — verify all extracted and manually entered closing values first."); return
        try:
            values = {key: field.text().strip() for key, field in self.fields.items()}
            outcome = NextDayBiasEngine().analyze(values)
            evidence = "\n• ".join(outcome["evidence"])
            self.result.setText(
                f"{self.index.currentText()} NEXT-DAY BIAS: {outcome['bias']} | Confidence: {outcome['confidence']}%\n"
                f"Probable evidence zone: {outcome['lower']:,.2f} to {outcome['upper']:,.2f}\n"
                f"Put-OI support: {outcome['support']:,.2f} | Call-OI resistance: {outcome['resistance']:,.2f}\n"
                f"Bullish acceptance above: {outcome['bullish_above']:,.2f} | Bearish acceptance below: {outcome['bearish_below']:,.2f}\n"
                f"Evidence:\n• {evidence}\n\nRevalidate after the first completed 15-minute candle. Overnight news and gaps can invalidate this bias."
            )
        except (KeyError, ValueError):
            self.result.setText("INPUT ERROR — enter positive verified chart values, Put support below Call resistance, and valid numeric PCR/premiums.")
