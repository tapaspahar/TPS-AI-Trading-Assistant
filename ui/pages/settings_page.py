from threading import Thread

from PySide6.QtCore import QTime, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QTimeEdit, QVBoxLayout, QWidget, QGridLayout,
)

from core.settings_store import SettingsStore
from services.broker_registry import (
    BROKERS, broker_credentials_complete, broker_definition, create_broker_client,
)
from services.credential_store import BrokerCredentialStore
from services.live_session import LiveSession
from ui.themes.theme_manager import apply_theme
from ui.themes.ui_styles import UI_STYLE_NAMES
from services.notification_service import NOTIFICATION_LABELS, NotificationService


class SettingsPage(QWidget):
    auto_connection_succeeded = Signal(object, str)
    auto_connection_failed = Signal(str)
    publisher_tokens_received = Signal(dict)
    live_connected = Signal()

    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        self.credential_store = BrokerCredentialStore()
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
        self.stop_min = QLineEdit(str(values["adaptive_stop_min_percent"]))
        self.stop_max = QLineEdit(str(values["adaptive_stop_max_percent"]))
        self.stop_sweep_buffer = QLineEdit(str(values["stop_sweep_buffer_percent"]))
        self.tps_match_mode = QComboBox()
        self.tps_match_mode.addItem("Adaptive - market regime decides applicable checks", "adaptive")
        self.tps_match_mode.addItem("Fixed Count - use configured required matches", "count")
        self.tps_match_mode.addItem("All Applicable - every applicable check must pass", "all")
        self.tps_match_mode.setCurrentIndex(max(0, self.tps_match_mode.findData(values["tps_match_mode"])))
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
                             ("Adaptive stop minimum breathing room (%)", self.stop_min),
                             ("Adaptive stop maximum (%)", self.stop_max),
                             ("Wick / liquidity sweep buffer (%)", self.stop_sweep_buffer),
                             ("TPS checklist match mode", self.tps_match_mode),
                             ("Colour Theme", self.theme), ("UI Design Style", self.ui_style)):
            field.setMinimumHeight(36)
            form.addRow(label, field)
        layout.addLayout(form)
        stop_note = QLabel(
            "Release 1.5.1: TPS fixed chhota stop force nahi karta. Stop volatility regime, spread aur wick/sweep buffer se banta hai; "
            "wider stop par quantity kam hoti hai. Ek lot risk cap me fit na ho toh trade skip hota hai. Stop hunting guaranteed fact nahi—saved candles me wick sweep aur genuine invalidation alag review honge."
        )
        stop_note.setWordWrap(True); layout.addWidget(stop_note)
        self.theme_hint = QLabel("Choose any colour theme plus one of 10 UI design systems. The combination previews instantly; press Save Settings to keep it for the next launch.")
        self.theme_hint.setWordWrap(True)
        layout.addWidget(self.theme_hint)
        timing_box = QGroupBox("Market Timing")
        timing_form = QFormLayout(timing_box)
        timing_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.market_pre_open = QTimeEdit(QTime.fromString(values["market_pre_open_time"], "HH:mm"))
        self.market_open = QTimeEdit(QTime.fromString(values["market_open_time"], "HH:mm"))
        self.market_close = QTimeEdit(QTime.fromString(values["market_close_time"], "HH:mm"))
        for field in (self.market_pre_open, self.market_open, self.market_close):
            field.setDisplayFormat("HH:mm")
            field.setMinimumHeight(36)
            field.setAccelerated(False)
        timing_form.addRow("Pre-open starts", self.market_pre_open)
        timing_form.addRow("Regular trading starts", self.market_open)
        timing_form.addRow("Market closes", self.market_close)
        timing_note = QLabel(
            "These times control TPS countdowns, completed-candle monitoring and fresh-entry safety windows. "
            "They do not change the broker or exchange clock. Update them only after an official market-timing change."
        )
        timing_note.setWordWrap(True)
        timing_form.addRow(timing_note)
        layout.addWidget(timing_box)
        execution_box = QGroupBox("Order Mode & Default Exit Plan — Release 1.5.1")
        execution_form = QFormLayout(execution_box)
        self.execution_mode = QComboBox()
        self.execution_mode.addItem("Paper order / plan (recommended)", "PAPER")
        self.execution_mode.addItem("Real broker order — safeguards required", "REAL")
        self.execution_mode.setCurrentIndex(max(0, self.execution_mode.findData(values.get("execution_mode", "PAPER"))))
        self.execution_target_basis = QComboBox()
        self.execution_stop_basis = QComboBox()
        for widget in (self.execution_target_basis, self.execution_stop_basis):
            widget.addItem("Exact exit price", "PRICE")
            widget.addItem("Rupee move from entry", "AMOUNT")
            widget.addItem("Percentage move from entry", "PERCENT")
        self.execution_target_basis.setCurrentIndex(max(0, self.execution_target_basis.findData(values.get("execution_target_basis", "PERCENT"))))
        self.execution_stop_basis.setCurrentIndex(max(0, self.execution_stop_basis.findData(values.get("execution_stop_basis", "PERCENT"))))
        self.execution_target_value = QLineEdit(str(values.get("execution_target_value", 20.0)))
        self.execution_stop_value = QLineEdit(str(values.get("execution_stop_value", 10.0)))
        self.execution_time_exit_enabled = QCheckBox("Enable planned time exit")
        self.execution_time_exit_enabled.setChecked(bool(values.get("execution_time_exit_enabled", True)))
        self.execution_time_exit = QTimeEdit(QTime.fromString(values.get("execution_time_exit", "15:20"), "HH:mm"))
        self.execution_time_exit.setDisplayFormat("HH:mm")
        execution_form.addRow("Active order mode", self.execution_mode)
        execution_form.addRow("Target input type", self.execution_target_basis)
        execution_form.addRow("Target value", self.execution_target_value)
        execution_form.addRow("Stop-loss input type", self.execution_stop_basis)
        execution_form.addRow("Stop-loss value", self.execution_stop_value)
        execution_form.addRow(self.execution_time_exit_enabled)
        execution_form.addRow("Planned exit time", self.execution_time_exit)
        execution_note = QLabel(
            "Paper is the safe default. Selecting Real only changes the preferred workflow; it does not authorize money movement. "
            "Real submission still needs the saved opt-in, two session-only safety ticks and a final confirmation. Expiry After 3 PM pair execution also uses two explicit safety ticks; auto execution resets OFF on every launch. "
            "Its combined target, maximum loss and time exit submit guarded exits for both legs, but broker fills are never atomic or guaranteed—always verify partial/rejected orders in the broker app."
        )
        execution_note.setWordWrap(True); execution_form.addRow(execution_note)
        layout.addWidget(execution_box)
        save = QPushButton("Save Settings")
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addWidget(QLabel("Settings are stored only on this computer. Saving settings never places an order; real submission is separately locked inside Broker Execution."))
        recovery_box = QGroupBox("Release 1.3 - Overtrading Protection")
        recovery_layout = QVBoxLayout(recovery_box)
        recovery_note = QLabel(
            f"Recovery Mode is active by default: maximum {values['recovery_daily_trade_limit']} new paper capture/day, "
            f"{values['recovery_lock_hours']}-hour cooling after {values['recovery_loss_streak_limit']} consecutive "
            f"paper losses, and {values['recovery_min_paper_sessions']} separate paper sessions before real-money "
            "eligibility can be reviewed. Daily check-in and current lock status are available in Overtrading Protection Center."
        )
        recovery_note.setWordWrap(True)
        recovery_layout.addWidget(recovery_note)
        layout.addWidget(recovery_box)
        notification_box = QGroupBox("Notification Center - desktop alerts")
        notification_layout = QVBoxLayout(notification_box)
        self.notifications_enabled = QCheckBox("Enable TPS desktop notifications")
        self.notifications_enabled.setChecked(values["notifications_enabled"])
        self.notification_sound = QCheckBox("Play notification sound")
        self.notification_sound.setChecked(values["notification_sound"])
        notification_layout.addWidget(self.notifications_enabled)
        notification_layout.addWidget(self.notification_sound)
        notification_note = QLabel(
            "Choose which page or trading event may show a Windows desktop alert. Routine 5-minute rejections are OFF by default to avoid popup noise."
        )
        notification_note.setWordWrap(True)
        notification_layout.addWidget(notification_note)
        notification_grid = QGridLayout()
        notification_grid.setHorizontalSpacing(18)
        notification_grid.setVerticalSpacing(6)
        self.notification_checks = {}
        preferences = values["notification_preferences"]
        for index, (key, label) in enumerate(NOTIFICATION_LABELS.items()):
            check = QCheckBox(label)
            if key == "early_watch":
                check.setToolTip(
                    "Early Watch is a near-qualified completed-candle observation, not a trade signal. "
                    "It alerts before FIRST VALID so timing can be studied; all final strategy and safety checks still apply."
                )
            check.setChecked(bool(preferences.get(key, False)))
            self.notification_checks[key] = check
            notification_grid.addWidget(check, index // 3, index % 3)
        notification_layout.addLayout(notification_grid)
        test_notification = QPushButton("Send Test Desktop Notification")
        test_notification.clicked.connect(lambda: NotificationService.instance().test())
        notification_layout.addWidget(test_notification)
        layout.addWidget(notification_box)
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
        broker_box = QGroupBox("Broker connection (market data; safeguarded execution where supported)")
        broker_form = QFormLayout(broker_box)
        broker_form.setContentsMargins(18, 28, 18, 16)
        broker_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        broker_form.setHorizontalSpacing(18)
        broker_form.setVerticalSpacing(12)
        self.broker_provider = QComboBox()
        for broker_id, definition in BROKERS.items():
            suffix = " — TPS adapter ready" if definition.adapter_available else " — credentials only; adapter required"
            self.broker_provider.addItem(definition.name + suffix, broker_id)
        self.broker_provider.setCurrentIndex(max(0, self.broker_provider.findData(values.get("broker_provider", "angel_one"))))
        self.broker_provider.setMinimumHeight(36)
        broker_form.addRow("Broker provider", self.broker_provider)
        self.credential_labels = []
        self.credential_fields = []
        for _index in range(6):
            label = QLabel()
            field = QLineEdit(); field.setMinimumHeight(36)
            self.credential_labels.append(label); self.credential_fields.append(field)
            broker_form.addRow(label, field)
        self.broker_note = QLabel()
        self.broker_note.setWordWrap(True)
        broker_form.addRow(self.broker_note)
        self.broker_status = QLabel("Connection status: not connected")
        self.broker_status.setWordWrap(True)
        self.broker_status.setMinimumHeight(24)
        broker_form.addRow(self.broker_status)
        save_credentials = QPushButton("Save Credentials Securely")
        save_credentials.clicked.connect(self.save_broker_credentials)
        forget_credentials = QPushButton("Remove Saved Credentials")
        forget_credentials.clicked.connect(self.clear_broker_credentials)
        credential_actions = QWidget()
        credential_actions_layout = QHBoxLayout(credential_actions)
        credential_actions_layout.setContentsMargins(0, 0, 0, 0)
        credential_actions_layout.setSpacing(10)
        credential_actions_layout.addWidget(save_credentials)
        credential_actions_layout.addWidget(forget_credentials, 1)
        broker_form.addRow(credential_actions)
        self.open_broker_login = QPushButton("Open Official Broker Setup / Login")
        self.open_broker_login.clicked.connect(self.open_selected_broker_login)
        self.open_broker_login.setMinimumHeight(38)
        broker_form.addRow(self.open_broker_login)
        self.official_broker_connect = QPushButton("Connect with Angel One — Official Login")
        self.official_broker_connect.clicked.connect(self.start_angel_one_publisher_login)
        self.official_broker_connect.setMinimumHeight(42)
        broker_form.addRow(self.official_broker_connect)
        connect = QPushButton("Connect Live Data")
        connect.clicked.connect(self.connect_broker)
        connect.setMinimumHeight(38)
        broker_form.addRow(connect)
        layout.addWidget(broker_box)
        self.broker_provider.currentIndexChanged.connect(self.on_broker_changed)
        self.on_broker_changed()
        layout.addStretch()
        self.auto_connection_succeeded.connect(self.complete_auto_connection)
        self.auto_connection_failed.connect(self.show_auto_connection_error)
        self.publisher_tokens_received.connect(self.verify_angel_one_publisher_session)
        self._auto_connection_started = False
        self._publisher_login = None
        self._publisher_api_key = ""

    def save(self):
        try:
            self.store.save({
                "capital": self.capital.text(), "risk_percent": self.risk_percent.text(),
                "daily_loss_percent": self.daily_loss_percent.text(), "max_trades_per_day": self.max_trades.text(),
                "market_pre_open_time": self.market_pre_open.time().toString("HH:mm"),
                "market_open_time": self.market_open.time().toString("HH:mm"),
                "market_close_time": self.market_close.time().toString("HH:mm"),
                "execution_mode": self.execution_mode.currentData(),
                "execution_target_basis": self.execution_target_basis.currentData(),
                "execution_target_value": self.execution_target_value.text(),
                "execution_stop_basis": self.execution_stop_basis.currentData(),
                "execution_stop_value": self.execution_stop_value.text(),
                "execution_time_exit_enabled": self.execution_time_exit_enabled.isChecked(),
                "execution_time_exit": self.execution_time_exit.time().toString("HH:mm"),
                "paper_trade_cooldown_minutes": self.cooldown.text(), "minimum_rr_ratio": self.minimum_rr.text(),
                "maximum_option_spread_percent": self.max_spread.text(), "minimum_option_volume": self.minimum_volume.text(),
                "adaptive_stop_min_percent": self.stop_min.text(), "adaptive_stop_max_percent": self.stop_max.text(),
                "stop_sweep_buffer_percent": self.stop_sweep_buffer.text(),
                "tps_match_mode": self.tps_match_mode.currentData(),
                "economic_calendar_enabled": self.calendar_enabled.isChecked(),
                "economic_calendar_api_key": self.calendar_key.text(), "event_feed_fail_closed": self.fail_closed.isChecked(),
                "trailing_stop_enabled": self.trailing_enabled.isChecked(), "trailing_stop_trigger_r": self.trailing_trigger.text(),
                "trailing_stop_lock_r": self.trailing_lock.text(), "time_exit_minutes_before_close": self.time_exit.text(),
                "theme": self.theme.currentData(),
                "ui_style": self.ui_style.currentData(),
                "broker_provider": self.broker_provider.currentData(),
                "notifications_enabled": self.notifications_enabled.isChecked(),
                "notification_sound": self.notification_sound.isChecked(),
                "notification_preferences": {
                    key: check.isChecked() for key, check in self.notification_checks.items()
                },
            })
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        apply_theme(QApplication.instance(), self.theme.currentData(), self.ui_style.currentData())
        QMessageBox.information(self, "Settings saved", "Settings, theme, and desktop notification choices have been saved locally.")

    def preview_theme(self):
        """Preview the selected visual style; persistence remains an explicit Save action."""
        apply_theme(QApplication.instance(), self.theme.currentData(), self.ui_style.currentData())

    def current_broker_credentials(self):
        definition = broker_definition(self.broker_provider.currentData())
        return {
            key: self.credential_fields[index].text()
            for index, (key, _label, _secret) in enumerate(definition.fields)
        }

    def on_broker_changed(self):
        broker_id = self.broker_provider.currentData() or "angel_one"
        definition = broker_definition(broker_id)
        try:
            saved = self.credential_store.load(broker_id)
        except RuntimeError:
            saved = {}
        for index, (label_widget, field) in enumerate(zip(self.credential_labels, self.credential_fields)):
            visible = index < len(definition.fields)
            label_widget.setVisible(visible); field.setVisible(visible)
            if visible:
                key, label, secret = definition.fields[index]
                label_widget.setText(label)
                field.setEchoMode(QLineEdit.Password if secret else QLineEdit.Normal)
                field.setText(saved.get(key, ""))
            else:
                field.clear()
        if definition.adapter_available:
            if broker_id == "dhan":
                self.broker_note.setText(
                    "Dhan TPS adapter active (read-only). Save Client ID, Dhan PIN and the TOTP setup secret once. "
                    "TPS automatically generates a fresh 24-hour access token on startup and before expiry; "
                    "you do not need to paste a daily token."
                )
            elif broker_id == "paytm_money":
                self.broker_note.setText(
                    "Paytm Money adapter active (read-only). Enter API Key and API Secret, open Paytm Login, "
                    "authorize TPS, then paste request_token from the redirect URL and connect. TPS securely "
                    "stores the returned access/read/public tokens; expired authorization must be renewed in Paytm."
                )
            else:
                self.broker_note.setText(
                    f"{definition.name} TPS adapter active: candles, quotes, option chain and live feed are read-only."
                )
            self.broker_status.setText("Connection status: not connected")
        else:
            self.broker_note.setText(
                f"{definition.name} profile can be stored securely. Live connection requires its own TPS adapter because broker APIs and instrument tokens are different."
            )
            self.broker_status.setText("Connection status: adapter not installed")
        self.open_broker_login.setVisible(bool(definition.setup_url))
        self.open_broker_login.setText(
            "Open Paytm Authorization Login" if broker_id == "paytm_money" else f"Open Official {definition.name} API Setup"
        )
        self.official_broker_connect.setVisible(broker_id == "angel_one")
        if definition.login_summary:
            self.broker_note.setText(
                definition.login_summary
                + " Broker ID alone cannot fetch market data because the broker must issue an authenticated API session. "
                "TPS keeps the advanced values in Windows Credential Manager, never in GitHub."
            )

    def start_angel_one_publisher_login(self):
        """Open Angel One's page; TPS never receives broker PIN or TOTP."""
        if self.broker_provider.currentData() != "angel_one":
            return
        api_key = self.current_broker_credentials().get("api_key", "").strip()
        if not api_key:
            QMessageBox.warning(
                self, "Angel One official login",
                "Enter your Angel One SmartAPI App API Key first. The callback URL registered in SmartAPI My Apps must be "
                "http://127.0.0.1:8765/angel-one/callback",
            )
            return
        try:
            from services.angel_one_publisher_login import AngelOnePublisherLogin
            self._publisher_login = AngelOnePublisherLogin(api_key)
            url = self._publisher_login.start(
                lambda tokens: self.publisher_tokens_received.emit(tokens),
                lambda message: self.auto_connection_failed.emit(message),
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Angel One official login", str(error))
            return
        self._publisher_api_key = api_key
        self.broker_status.setText("Connection status: waiting for authorization on official Angel One page…")
        if not QDesktopServices.openUrl(QUrl(url)):
            self.broker_status.setText("Connection status: official Angel One login page could not be opened")

    def verify_angel_one_publisher_session(self, tokens):
        self.broker_status.setText("Connection status: authorization received; verifying funds and data access…")
        Thread(target=self._verify_angel_one_publisher_session, args=(dict(tokens),), daemon=True).start()

    def _verify_angel_one_publisher_session(self, tokens):
        try:
            from services.angel_one_client import AngelOneClient
            client = AngelOneClient.from_publisher_tokens(
                self._publisher_api_key, tokens.get("auth_token", ""),
                tokens.get("feed_token", ""), tokens.get("client_code", ""),
            )
            self.credential_store.save_session("angel_one", {**tokens, "api_key": self._publisher_api_key})
        except (ValueError, RuntimeError) as error:
            self.auto_connection_failed.emit(str(error))
            return
        self.auto_connection_succeeded.emit(client, "angel_one")

    def open_selected_broker_login(self):
        broker_id = self.broker_provider.currentData()
        definition = broker_definition(broker_id)
        url = definition.setup_url
        if broker_id == "paytm_money":
            credentials = self.current_broker_credentials()
            try:
                from services.paytm_money_client import PaytmMoneyClient
                url = PaytmMoneyClient(credentials.get("api_key", ""), credentials.get("api_secret", "")).login_url()
            except ValueError:
                # First-time users must create/authorize their developer app before a login URL exists.
                url = definition.setup_url
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, f"{definition.name} setup", "The official broker setup page could not be opened.")

    def _save_selected_provider(self):
        values = self.store.load()
        values["broker_provider"] = self.broker_provider.currentData()
        self.store.save(values)

    def save_broker_credentials(self):
        broker_id = self.broker_provider.currentData()
        try:
            self.credential_store.save(broker_id, self.current_broker_credentials())
            self._save_selected_provider()
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Secure credential storage", str(error))
            return
        QMessageBox.information(
            self, "Credentials saved",
            f"{broker_definition(broker_id).name} profile saved in Windows Credential Manager. It is not saved in the project, database, or GitHub.",
        )

    def clear_broker_credentials(self):
        broker_id = self.broker_provider.currentData()
        try:
            self.credential_store.clear(broker_id)
            self.credential_store.clear_session(broker_id)
        except RuntimeError as error:
            QMessageBox.warning(self, "Secure credential storage", str(error))
            return
        for field in self.credential_fields:
            field.clear()
        QMessageBox.information(self, "Credentials removed", f"Saved {broker_definition(broker_id).name} credentials have been removed.")

    def connect_broker(self):
        broker_id = self.broker_provider.currentData()
        definition = broker_definition(broker_id)
        try:
            client = create_broker_client(broker_id, self.current_broker_credentials())
            result = client.connect()
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, f"{definition.name} connection", str(error))
            return
        LiveSession.client = client
        LiveSession.broker_id = broker_id
        self._persist_generated_credentials(broker_id, client)
        self.broker_status.setText("Connection status: connected (read-only)")
        self.live_connected.emit()
        QMessageBox.information(self, definition.name, result["message"])

    def auto_connect_saved_credentials(self):
        """Restore a read-only session on startup when the user opted to save credentials."""
        if LiveSession.connected() or self._auto_connection_started:
            return
        try:
            broker_id = self.store.load().get("broker_provider", "angel_one")
            credentials = self.credential_store.load(broker_id)
            publisher_session = self.credential_store.load_session("angel_one") if broker_id == "angel_one" else {}
        except RuntimeError as error:
            self.broker_status.setText(f"Connection status: secure storage unavailable ({error})")
            return
        definition = broker_definition(broker_id)
        if broker_id == "angel_one" and publisher_session.get("api_key") and publisher_session.get("auth_token") and publisher_session.get("feed_token"):
            self.broker_status.setText("Connection status: restoring official Angel One session…")
            self._auto_connection_started = True
            Thread(target=self._connect_saved_publisher_session, args=(publisher_session,), daemon=True).start()
            return
        if not broker_credentials_complete(broker_id, credentials):
            self.broker_status.setText("Connection status: save credentials once to enable auto-connect")
            return
        self.broker_status.setText("Connection status: connecting saved credentials…")
        self._auto_connection_started = True
        Thread(target=self._connect_saved_credentials, args=(broker_id, credentials), daemon=True).start()

    def _connect_saved_publisher_session(self, values):
        try:
            from services.angel_one_client import AngelOneClient
            client = AngelOneClient.from_publisher_tokens(
                values.get("api_key", ""), values.get("auth_token", ""),
                values.get("feed_token", ""), values.get("client_code", ""),
            )
        except (ValueError, RuntimeError) as error:
            try:
                self.credential_store.clear_session("angel_one")
            except RuntimeError:
                pass
            self.auto_connection_failed.emit(f"saved Angel One session expired; use Official Login ({error})")
            return
        self.auto_connection_succeeded.emit(client, "angel_one")

    def _connect_saved_credentials(self, broker_id, credentials):
        try:
            client = create_broker_client(broker_id, credentials)
            result = client.connect()
        except (ValueError, RuntimeError) as error:
            self.auto_connection_failed.emit(str(error))
            return
        self.auto_connection_succeeded.emit(client, broker_id)

    def complete_auto_connection(self, client, broker_id):
        LiveSession.client = client
        LiveSession.broker_id = broker_id
        self._persist_generated_credentials(broker_id, client)
        self.broker_status.setText("Connection status: connected automatically (read-only)")
        self.live_connected.emit()

    def _persist_generated_credentials(self, broker_id, client):
        exporter = getattr(client, "export_credentials", None)
        if not callable(exporter):
            return
        try:
            credentials = exporter()
            self.credential_store.save(broker_id, credentials)
        except (ValueError, RuntimeError):
            return
        if self.broker_provider.currentData() == broker_id:
            definition = broker_definition(broker_id)
            for index, (key, _label, _secret) in enumerate(definition.fields):
                self.credential_fields[index].setText(credentials.get(key, ""))

    def show_auto_connection_error(self, message):
        self.broker_status.setText(f"Connection status: auto-connect failed ({message})")
