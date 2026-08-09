from threading import Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.settings_store import SettingsStore
from services.angel_one_client import AngelOneClient
from services.credential_store import AngelOneCredentialStore
from services.live_session import LiveSession
from ui.themes.theme_manager import apply_theme
from ui.themes.ui_styles import UI_STYLE_NAMES


class SettingsPage(QWidget):
    auto_connection_succeeded = Signal(object, str)
    auto_connection_failed = Signal(str)
    live_connected = Signal()

    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        self.credential_store = AngelOneCredentialStore()
        values = self.store.load()
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(12, 10, 12, 14)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll.setWidget(self.content)
        shell.addWidget(self.scroll)
        layout.addWidget(QLabel("Risk Settings"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.capital = QLineEdit(str(values["capital"]))
        self.risk_percent = QLineEdit(str(values["risk_percent"]))
        self.daily_loss_percent = QLineEdit(str(values["daily_loss_percent"]))
        self.max_trades = QLineEdit(str(values["max_trades_per_day"]))
        self.cooldown = QLineEdit(str(values["paper_trade_cooldown_minutes"]))
        self.minimum_rr = QLineEdit(str(values["minimum_rr_ratio"]))
        self.max_spread = QLineEdit(str(values["maximum_option_spread_percent"]))
        self.minimum_volume = QLineEdit(str(values["minimum_option_volume"]))
        self.theme = QComboBox()
        self.theme.addItem("Midnight Blue  •  focused trading terminal", "dark")
        self.theme.addItem("Arctic Light  •  clean daylight workspace", "light")
        self.theme.addItem("Emerald Pulse  •  calm market green", "emerald")
        self.theme.addItem("Sunset Copper  •  warm premium light", "sunset")
        self.theme.setCurrentIndex(max(0, self.theme.findData(values["theme"])))
        self.theme.currentIndexChanged.connect(self.preview_theme)
        self.ui_style = QComboBox()
        style_descriptions = {
            "skeuomorphism": "realistic depth and tactile controls",
            "neomorphism": "soft raised surfaces",
            "glassmorphism": "translucent layered glass",
            "claymorphism": "rounded playful clay surfaces",
            "minimalism": "clean and distraction-free",
            "maximalism": "bold colour and rich detail",
            "brutalism": "raw high-contrast geometry",
            "liquid_glass": "fluid translucent capsules",
            "bento_grid": "structured modular cards",
            "spatial_ui": "floating depth-first workspace",
        }
        for key, name in UI_STYLE_NAMES.items():
            self.ui_style.addItem(f"{name}  -  {style_descriptions[key]}", key)
        self.ui_style.setCurrentIndex(max(0, self.ui_style.findData(values["ui_style"])))
        self.ui_style.currentIndexChanged.connect(self.preview_theme)
        for label, field in (("Account capital", self.capital), ("Risk per trade (%)", self.risk_percent),
                             ("Daily loss limit (%)", self.daily_loss_percent), ("Maximum trades per day", self.max_trades),
                             ("Paper-trade cooldown (minutes)", self.cooldown), ("Minimum risk:reward", self.minimum_rr),
                             ("Maximum option spread (%)", self.max_spread), ("Minimum option volume", self.minimum_volume),
                             ("Colour Theme", self.theme), ("UI Design Style", self.ui_style)):
            field.setMinimumHeight(36)
            form.addRow(label, field)
        layout.addLayout(form)
        self.theme_hint = QLabel("Choose any colour theme plus one of 10 UI design systems. The combination previews instantly; press Save Settings to keep it for the next launch.")
        self.theme_hint.setWordWrap(True)
        layout.addWidget(self.theme_hint)
        save = QPushButton("Save Settings")
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addWidget(QLabel("Settings are stored only on this computer. They do not connect to a broker or place trades."))
        safety_box = QGroupBox("Economic calendar and lifecycle safety")
        safety_form = QFormLayout(safety_box)
        self.calendar_enabled = QCheckBox("Use automatic economic calendar")
        self.calendar_enabled.setChecked(values["economic_calendar_enabled"])
        self.calendar_key = QLineEdit(values["economic_calendar_api_key"]); self.calendar_key.setEchoMode(QLineEdit.Password)
        self.calendar_key.setPlaceholderText("Trading Economics API key (optional; provider account required)")
        self.fail_closed = QCheckBox("Block auto entries if calendar feed is unavailable")
        self.fail_closed.setChecked(values["event_feed_fail_closed"])
        self.trailing_enabled = QCheckBox("Enable premium trailing stop")
        self.trailing_enabled.setChecked(values["trailing_stop_enabled"])
        self.trailing_trigger = QLineEdit(str(values["trailing_stop_trigger_r"]))
        self.trailing_lock = QLineEdit(str(values["trailing_stop_lock_r"]))
        self.time_exit = QLineEdit(str(values["time_exit_minutes_before_close"]))
        safety_form.addRow(self.calendar_enabled); safety_form.addRow("Calendar API key", self.calendar_key)
        safety_form.addRow(self.fail_closed); safety_form.addRow(self.trailing_enabled)
        safety_form.addRow("Trail trigger (R)", self.trailing_trigger); safety_form.addRow("Trail lock (R)", self.trailing_lock)
        safety_form.addRow("Time exit before close (minutes)", self.time_exit)
        safety_note = QLabel("Calendar source: Trading Economics API. If no key is configured, TPS clearly reports feed unavailable and uses the emergency News Risk switch; it never invents an event.")
        safety_note.setWordWrap(True); safety_form.addRow(safety_note)
        layout.addWidget(safety_box)
        broker_box = QGroupBox("Angel One live data")
        broker_form = QFormLayout(broker_box)
        broker_form.setContentsMargins(18, 28, 18, 16)
        broker_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        broker_form.setHorizontalSpacing(18)
        broker_form.setVerticalSpacing(12)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.client_code = QLineEdit()
        self.mpin = QLineEdit(); self.mpin.setEchoMode(QLineEdit.Password)
        self.totp_secret = QLineEdit(); self.totp_secret.setEchoMode(QLineEdit.Password)
        for label, field in (("API Key", self.api_key), ("Client Code", self.client_code), ("MPIN", self.mpin), ("TOTP secret", self.totp_secret)):
            field.setMinimumHeight(36)
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
        self.broker_status.setWordWrap(True)
        self.broker_status.setMinimumHeight(24)
        broker_form.addRow(self.broker_status)
        save_credentials = QPushButton("Save Credentials Securely")
        save_credentials.clicked.connect(self.save_angel_credentials)
        forget_credentials = QPushButton("Remove Saved Credentials")
        forget_credentials.clicked.connect(self.clear_angel_credentials)
        credential_actions = QWidget()
        credential_actions_layout = QHBoxLayout(credential_actions)
        credential_actions_layout.setContentsMargins(0, 0, 0, 0)
        credential_actions_layout.setSpacing(10)
        credential_actions_layout.addWidget(save_credentials)
        credential_actions_layout.addWidget(forget_credentials, 1)
        broker_form.addRow(credential_actions)
        connect = QPushButton("Connect Live Data")
        connect.clicked.connect(self.connect_angel_one)
        connect.setMinimumHeight(38)
        broker_form.addRow(connect)
        layout.addWidget(broker_box)
        layout.addStretch()
        self.auto_connection_succeeded.connect(self.complete_auto_connection)
        self.auto_connection_failed.connect(self.show_auto_connection_error)
        self._auto_connection_started = False

    def save(self):
        try:
            self.store.save({
                "capital": self.capital.text(), "risk_percent": self.risk_percent.text(),
                "daily_loss_percent": self.daily_loss_percent.text(), "max_trades_per_day": self.max_trades.text(),
                "paper_trade_cooldown_minutes": self.cooldown.text(), "minimum_rr_ratio": self.minimum_rr.text(),
                "maximum_option_spread_percent": self.max_spread.text(), "minimum_option_volume": self.minimum_volume.text(),
                "economic_calendar_enabled": self.calendar_enabled.isChecked(),
                "economic_calendar_api_key": self.calendar_key.text(), "event_feed_fail_closed": self.fail_closed.isChecked(),
                "trailing_stop_enabled": self.trailing_enabled.isChecked(), "trailing_stop_trigger_r": self.trailing_trigger.text(),
                "trailing_stop_lock_r": self.trailing_lock.text(), "time_exit_minutes_before_close": self.time_exit.text(),
                "theme": self.theme.currentData(),
                "ui_style": self.ui_style.currentData(),
            })
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        apply_theme(QApplication.instance(), self.theme.currentData(), self.ui_style.currentData())
        QMessageBox.information(self, "Settings saved", "Settings, colour theme, and UI design style have been saved locally.")

    def preview_theme(self):
        """Preview the selected visual style; persistence remains an explicit Save action."""
        apply_theme(QApplication.instance(), self.theme.currentData(), self.ui_style.currentData())

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
        self.live_connected.emit()
        QMessageBox.information(self, "Angel One", result["message"])

    def auto_connect_saved_credentials(self):
        """Restore a read-only session on startup when the user opted to save credentials."""
        if LiveSession.connected() or self._auto_connection_started:
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
        self._auto_connection_started = True
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
        self.live_connected.emit()

    def show_auto_connection_error(self, message):
        self.broker_status.setText(f"Connection status: auto-connect failed ({message})")
