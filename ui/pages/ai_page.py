from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from engine.psychology_engine import PsychologyEngine


class AIPage(QWidget):
    """A transparent pre-trade confirmation score, not financial advice."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("AI Trade Coach — confirmation score only"))
        self.checks = []
        for label, points in (("Trend confirmed", 20), ("VWAP confirmed", 15), ("EMA aligned", 10),
                              ("Volume confirmed", 15), ("Option-chain/OI confirmed", 20)):
            check = QCheckBox(f"{label} (+{points})")
            self.checks.append((check, points))
            layout.addWidget(check)
        psychology_row = QHBoxLayout()
        psychology_row.addWidget(QLabel("Psychology"))
        self.psychology = QComboBox()
        self.psychology.addItems(["Calm", "Confident", "Fear", "Greed", "FOMO", "Revenge"])
        psychology_row.addWidget(self.psychology)
        layout.addLayout(psychology_row)
        button = QPushButton("Calculate Score")
        button.clicked.connect(self.calculate)
        layout.addWidget(button)
        self.result = QLabel("Select confirmations to calculate.")
        layout.addWidget(self.result)
        layout.addStretch()

    def calculate(self):
        score = sum(points for check, points in self.checks if check.isChecked())
        score += PsychologyEngine().evaluate(self.psychology.currentText())
        decision = "STRONG BUY" if score >= 90 else "BUY" if score >= 75 else "WATCH" if score >= 60 else "NO TRADE"
        self.result.setText(f"Score: {score}/100\nDecision: {decision}\nUse this as a checklist, not investment advice.")
