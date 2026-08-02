from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from services.angel_one_client import AngelOneClient
from services.live_session import LiveSession


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
        broker_box = QGroupBox("Angel One live data (session-only)")
        broker_form = QFormLayout(broker_box)
        self.api_key = QLineEdit()
        self.client_code = QLineEdit()
        self.mpin = QLineEdit(); self.mpin.setEchoMode(QLineEdit.Password)
        self.totp_secret = QLineEdit(); self.totp_secret.setEchoMode(QLineEdit.Password)
        for label, field in (("API Key", self.api_key), ("Client Code", self.client_code), ("MPIN", self.mpin), ("TOTP secret", self.totp_secret)):
            broker_form.addRow(label, field)
        connect = QPushButton("Connect Live Data")
        connect.clicked.connect(self.connect_angel_one)
        broker_form.addRow(connect)
        layout.addWidget(broker_box)
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

    def connect_angel_one(self):
        try:
            client = AngelOneClient(self.api_key.text(), self.client_code.text(), self.mpin.text(), self.totp_secret.text())
            result = client.connect()
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Angel One connection", str(error))
            return
        LiveSession.client = client
        QMessageBox.information(self, "Angel One", result["message"])
