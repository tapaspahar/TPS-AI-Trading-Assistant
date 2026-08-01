from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.settings_store import SettingsStore


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        values = self.store.load()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Risk Settings"))
        form = QFormLayout()
        self.capital = QLineEdit(str(values["capital"]))
        self.risk_percent = QLineEdit(str(values["risk_percent"]))
        self.daily_loss_percent = QLineEdit(str(values["daily_loss_percent"]))
        self.max_trades = QLineEdit(str(values["max_trades_per_day"]))
        for label, field in (("Account capital", self.capital), ("Risk per trade (%)", self.risk_percent),
                             ("Daily loss limit (%)", self.daily_loss_percent), ("Maximum trades per day", self.max_trades)):
            form.addRow(label, field)
        layout.addLayout(form)
        save = QPushButton("Save Settings")
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addWidget(QLabel("Settings are stored only on this computer. They do not connect to a broker or place trades."))
        layout.addStretch()

    def save(self):
        try:
            self.store.save({
                "capital": self.capital.text(), "risk_percent": self.risk_percent.text(),
                "daily_loss_percent": self.daily_loss_percent.text(), "max_trades_per_day": self.max_trades.text(),
            })
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        QMessageBox.information(self, "Settings saved", "Risk settings have been saved locally.")
