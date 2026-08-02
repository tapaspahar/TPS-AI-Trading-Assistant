from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from engine.decision_engine import ChartSnapshot, DecisionEngine


class AIPage(QWidget):
    """Decision Engine V1 for the permanent TPS indicator profile."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Decision Engine V1 — verify values before acting"))
        layout.addWidget(QLabel("EMA 5 Pink | EMA 20 Violet | EMA 50 White | VWAP Yellow | SuperTrend | Volume EMA 20"))
        form = QFormLayout()
        self.fields = {}
        for key, label in (("price", "Current price"), ("ema_5", "EMA 5"), ("ema_20", "EMA 20"),
                           ("ema_50", "EMA 50"), ("vwap", "VWAP"), ("supertrend", "SuperTrend"),
                           ("volume", "Volume"), ("volume_ema", "Volume EMA 20")):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)
        self.option = QComboBox(); self.option.addItems(["CE", "PE"])
        self.psychology = QComboBox(); self.psychology.addItems(["Calm", "Confident", "Fear", "Greed", "FOMO", "Revenge"])
        form.addRow("Option", self.option)
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
            snapshot = ChartSnapshot(**{key: float(field.text()) for key, field in self.fields.items()})
            result = DecisionEngine().evaluate(snapshot, self.option.currentText(), self.psychology.currentText())
        except ValueError:
            self.result.setText("Enter numeric values for every chart field.")
            return
        reason_text = "\n".join(f"✓ {item}" for item in result["reasons"])
        warning_text = "\n".join(f"⚠ {item}" for item in result["warnings"])
        self.result.setText(f"Score: {result['score']}/100\nDirection: {result['direction']}\nDecision: {result['decision']}\n\n{reason_text}\n{warning_text}".strip())
