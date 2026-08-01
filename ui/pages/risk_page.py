from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from engine.risk_engine import RiskEngine
from core.settings_store import SettingsStore


class RiskPage(QWidget):
    """Position-sizing calculator. It never places an order."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Risk Manager"))
        form = QFormLayout()
        defaults = SettingsStore().load()
        self.capital = QLineEdit(str(defaults["capital"]))
        self.risk_percent = QLineEdit(str(defaults["risk_percent"]))
        self.entry = QLineEdit()
        self.stoploss = QLineEdit()
        self.target = QLineEdit()
        for label, field in (("Capital", self.capital), ("Risk per trade (%)", self.risk_percent),
                             ("Entry price", self.entry), ("Stop loss", self.stoploss), ("Target", self.target)):
            form.addRow(label, field)
        layout.addLayout(form)
        button = QPushButton("Calculate Position Size")
        button.clicked.connect(self.calculate)
        layout.addWidget(button)
        self.result = QLabel("Enter values to calculate quantity, maximum risk and R:R.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch()

    def calculate(self):
        try:
            capital, risk_percent = float(self.capital.text()), float(self.risk_percent.text())
            entry, stoploss, target = float(self.entry.text()), float(self.stoploss.text()), float(self.target.text())
            if capital <= 0 or not 0 < risk_percent <= 100 or entry <= 0 or entry == stoploss:
                raise ValueError
            quantity = RiskEngine().calculate_position_size(capital, risk_percent, entry, stoploss)
            max_risk = capital * risk_percent / 100
            rr = abs(target - entry) / abs(entry - stoploss)
            self.result.setText(f"Suggested quantity: {quantity}\nMaximum risk: ₹{max_risk:,.2f}\nRisk:Reward: 1:{rr:.2f}")
        except ValueError:
            self.result.setText("Use positive numbers. Entry and stop loss must be different.")
