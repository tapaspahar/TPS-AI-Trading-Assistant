from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from services.angel_one_client import AngelOneClient
from services.credential_store import AngelOneCredentialStore
from services.live_session import LiveSession
from ui.themes.theme_manager import apply_theme


class SettingsPage(QWidget):
    auto_connection_succeeded = Signal(object, str)
    auto_connection_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        self.credential_store = AngelOneCredentialStore()
        values = self.store.load()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Risk Settings"))
        form = QFormLayout()
        self.capital = QLineEdit(str(values["capital"]))
        self.risk_percent = QLineEdit(str(values["risk_percent"]))
        self.daily_loss_percent = QLineEdit(str(values["daily_loss_percent"]))
        self.max_trades = QLineEdit(str(values["max_trades_per_day"]))
        self.theme = QComboBox()
        self.theme.addItem("Dark theme", "dark")
        self.theme.addItem("Light theme", "light")
        self.theme.setCurrentIndex(0 if values["theme"] == "dark" else 1)
        for label, field in (("Account capital", self.capital), ("Risk per trade (%)", self.risk_percent),
                             ("Daily loss limit (%)", self.daily_loss_percent), ("Maximum trades per day", self.max_trades),
                             ("Appearance", self.theme)):
            form.addRow(label, field)
        layout.addLayout(form)
        save = QPushButton("Save Settings")
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addWidget(QLabel("Settings are stored only on this computer. They do not connect to a broker or place trades."))
        broker_box = QGroupBox("Angel One live data")
        broker_form = QFormLayout(broker_box)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.client_code = QLineEdit()
        self.mpin = QLineEdit(); self.mpin.setEchoMode(QLineEdit.Password)
        self.totp_secret = QLineEdit(); self.totp_secret.setEchoMode(QLineEdit.Password)
        for label, field in (("API Key", self.api_key), ("Client Code", self.client_code), ("MPIN", self.mpin), ("TOTP secret", self.totp_secret)):
            broker_form.addRow(label, field)
        try:
            saved_credentials = self.credential_store.load()
        except RuntimeError:
            saved_credentials = {}
        self.api_key.setText(saved_credentials.get("api_key", ""))
        self.client_code.setText(saved_credentials.get("client_code", ""))
        self.mpin.setText(saved_credentials.get("mpin", ""))
        self.totp_secret.setText(saved_credentials.get("totp_secret", ""))
        self.broker_status = QLabel("Connection status: not connected")
        broker_form.addRow(self.broker_status)
        save_credentials = QPushButton("Save Credentials Securely")
        save_credentials.clicked.connect(self.save_angel_credentials)
        forget_credentials = QPushButton("Remove Saved Credentials")
        forget_credentials.clicked.connect(self.clear_angel_credentials)
        broker_form.addRow(save_credentials, forget_credentials)
        connect = QPushButton("Connect Live Data")
        connect.clicked.connect(self.connect_angel_one)
        broker_form.addRow(connect)
        layout.addWidget(broker_box)
        layout.addStretch()
        self.auto_connection_succeeded.connect(self.complete_auto_connection)
        self.auto_connection_failed.connect(self.show_auto_connection_error)

    def save(self):
        try:
            self.store.save({
                "capital": self.capital.text(), "risk_percent": self.risk_percent.text(),
                "daily_loss_percent": self.daily_loss_percent.text(), "max_trades_per_day": self.max_trades.text(),
                "theme": self.theme.currentData(),
            })
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        apply_theme(QApplication.instance(), self.theme.currentData())
        QMessageBox.information(self, "Settings saved", "Settings and theme have been saved locally.")

    def save_angel_credentials(self):
        try:
            self.credential_store.save({
                "api_key": self.api_key.text(), "client_code": self.client_code.text(),
                "mpin": self.mpin.text(), "totp_secret": self.totp_secret.text(),
            })
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Secure credential storage", str(error))
            return
        QMessageBox.information(
            self, "Credentials saved",
            "Saved in Windows Credential Manager on this computer. They are not saved in the project, database, or GitHub.",
        )

    def clear_angel_credentials(self):
        try:
            self.credential_store.clear()
        except RuntimeError as error:
            QMessageBox.warning(self, "Secure credential storage", str(error))
            return
        for field in (self.api_key, self.client_code, self.mpin, self.totp_secret):
            field.clear()
        QMessageBox.information(self, "Credentials removed", "Saved Angel One credentials have been removed from this computer.")

    def connect_angel_one(self):
        try:
            client = AngelOneClient(self.api_key.text(), self.client_code.text(), self.mpin.text(), self.totp_secret.text())
            result = client.connect()
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Angel One connection", str(error))
            return
        LiveSession.client = client
        self.broker_status.setText("Connection status: connected (read-only)")
        QMessageBox.information(self, "Angel One", result["message"])

    def auto_connect_saved_credentials(self):
        """Restore a read-only session on startup when the user opted to save credentials."""
        if LiveSession.connected():
            return
        try:
            credentials = self.credential_store.load()
        except RuntimeError as error:
            self.broker_status.setText(f"Connection status: secure storage unavailable ({error})")
            return
        if not all(credentials.get(field) for field in ("api_key", "client_code", "mpin", "totp_secret")):
            self.broker_status.setText("Connection status: save credentials once to enable auto-connect")
            return
        self.broker_status.setText("Connection status: connecting saved credentials…")
        Thread(target=self._connect_saved_credentials, args=(credentials,), daemon=True).start()

    def _connect_saved_credentials(self, credentials):
        try:
            client = AngelOneClient(
                credentials["api_key"], credentials["client_code"], credentials["mpin"], credentials["totp_secret"],
            )
            result = client.connect()
        except (ValueError, RuntimeError) as error:
            self.auto_connection_failed.emit(str(error))
            return
        self.auto_connection_succeeded.emit(client, result["message"])

    def complete_auto_connection(self, client, message):
        LiveSession.client = client
        self.broker_status.setText("Connection status: connected automatically (read-only)")

    def show_auto_connection_error(self, message):
        self.broker_status.setText(f"Connection status: auto-connect failed ({message})")
