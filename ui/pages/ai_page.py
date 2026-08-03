from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from engine.decision_engine import ChartSnapshot, DecisionEngine


class AIPage(QWidget):
    """Decision Engine V1 for the permanent TPS indicator profile."""
    decision_ready = Signal(dict)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Decision Engine V1 — verify values before acting"))
        layout.addWidget(QLabel("EMA 5 Pink | EMA 20 Violet | EMA 50 White | VWAP Yellow | SuperTrend | Volume EMA 20"))
        form = QFormLayout()
        self.fields = {}
        self.loaded_symbol = ""
        for key, label in (("price", "Current price"), ("ema_5", "EMA 5"), ("ema_20", "EMA 20"),
                           ("ema_50", "EMA 50"), ("vwap", "VWAP"), ("rsi_14", "RSI 14"), ("atr_14", "ATR 14"), ("supertrend", "SuperTrend"),
                           ("volume", "Volume"), ("volume_ema", "Volume EMA 20")):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)
        self.option = QComboBox(); self.option.addItems(["CE", "PE"])
        self.psychology = QComboBox(); self.psychology.addItems(["Calm", "Confident", "Fear", "Greed", "FOMO", "Revenge"])
        form.addRow("Candidate option (auto)", self.option)
        form.addRow("Psychology", self.psychology)
        layout.addLayout(form)
        button = QPushButton("Evaluate Setup")
        button.clicked.connect(self.evaluate)
        layout.addWidget(button)
        self.result = QLabel("Enter verified chart values. This is decision support, not investment advice.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch()

    def evaluate(self):
        try:
            required = ("price", "ema_5", "ema_20", "ema_50", "supertrend")
            values = {}
            for key, field in self.fields.items():
                text = field.text().strip()
                if key in required:
                    values[key] = float(text)
                else:
                    values[key] = float(text) if text else None
            snapshot = ChartSnapshot(**values)
            candidate_option = "CE" if snapshot.price > snapshot.supertrend else "PE"
            self.option.setCurrentText(candidate_option)
            result = DecisionEngine().evaluate(snapshot, candidate_option, self.psychology.currentText())
        except ValueError:
            self.result.setText("Enter numeric values for price, EMA 5/20/50 and SuperTrend. A trade plan needs verified Volume and Volume EMA 20.")
            return
        reason_text = "\n".join(f"✓ {item}" for item in result["reasons"])
        warning_text = "\n".join(f"⚠ {item}" for item in result["warnings"])
        self.result.setText(f"Score: {result['score']}/100\nDirection: {result['direction']}\nDecision: {result['decision']}\n\n{reason_text}\n{warning_text}".strip())
        self.decision_ready.emit({
            "symbol": self.loaded_symbol,
            "score": result["score"], "direction": result["direction"], "decision": result["decision"],
            "reasons": result["reasons"], "warnings": result["warnings"],
            "volume_confirmed": result["volume_confirmed"], "trade_ready": result["trade_ready"],
        })

    def load_chart_capture(self, capture: dict):
        """Pre-fill Decision Engine fields from local Chart Capture OCR."""
        field_mapping = {
            "close": "price", "ema_5": "ema_5", "ema_20": "ema_20",
            "ema_50": "ema_50", "vwap": "vwap", "rsi_14": "rsi_14", "atr_14": "atr_14", "supertrend": "supertrend",
            "volume": "volume", "volume_ema": "volume_ema",
        }
        missing = []
        for source_key, target_key in field_mapping.items():
            value = str(capture.get(source_key, "")).strip()
            if value:
                self.fields[target_key].setText(value)
            else:
                missing.append(target_key.replace("_", " "))
        symbol = capture.get("symbol", "Unknown symbol")
        self.loaded_symbol = str(symbol).upper()
        self.evaluate()
