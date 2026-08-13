from datetime import date, datetime, timedelta
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from core.database_manager import Database
from engine.option_chain_engine import analyze_option_chain
from engine.tps_entry_confirmation import CONDITION_WEIGHTS
from engine.trade_plan_engine import create_review_plan
from engine.greeks_engine import calculate_greeks
from services.auto_paper_trader import run_auto_paper_cycle
from core.overtrading_guard import OvertradingGuard
from services.live_session import LiveSession
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, buying_risk, contracts_near_spot


class OptionsPage(QWidget):
    """Read-only option-buying workspace; broker order placement is intentionally absent."""
    contracts_loaded = Signal(object)
    load_error = Signal(str)
    quote_loaded = Signal(object)
    quote_error = Signal(str)
    chain_loaded = Signal(object)
    chain_error = Signal(str)
    trade_plan_ready = Signal(dict)
    open_chart_capture = Signal()
    paper_trade_captured = Signal(dict)
    paper_trade_closed = Signal(object)
    paper_trade_monitored = Signal(object)
    paper_trade_error = Signal(str)
    auto_paper_status = Signal(object)
    auto_paper_captured = Signal(object)
    auto_attempt_saved = Signal()

    def __init__(self):
        super().__init__()
        self.contracts = []
        self.spot_price = None
        self.chart_context = None
        self.chain_context = None
        self.current_plan = None
        self.chain_loading = False
        self.auto_refresh_pending = False
        self.paper_monitoring = False
        self.auto_paper_running = False
        self.last_auto_paper_bucket = None
        self.service = OptionContractService()
        self.db = Database()
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 18)
        layout.setSpacing(10)
        layout.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        self.scroll.setWidget(content)
        outer_layout.addWidget(self.scroll)
        layout.addWidget(QLabel("Options Decision Workspace — verify every condition before placing a manual broker order."))

        selection = QGroupBox("1. Choose a contract")
        form = QFormLayout(selection)
        form.setVerticalSpacing(8)
        self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.underlying.currentTextChanged.connect(lambda _symbol: self.update_plan_readiness())
        self.expiry = QComboBox(); self.expiry.currentIndexChanged.connect(self.populate_strikes)
        self.option_type = QComboBox(); self.option_type.addItems(("CE", "PE")); self.option_type.currentIndexChanged.connect(self.populate_strikes)
        self.strike = QComboBox(); self.strike.currentIndexChanged.connect(self.schedule_auto_refresh)
        self.strike.currentIndexChanged.connect(self.update_lot_quantity)
        self.lots = QSpinBox(); self.lots.setRange(1, 100); self.lots.setValue(1); self.lots.valueChanged.connect(self.update_lot_quantity)
        self.event_check = QComboBox()
        self.event_check.addItems(("Review news / event risk", "No known high-impact event", "High-impact event or expiry-day risk"))
        self.event_check.setCurrentText("No known high-impact event")
        self.event_check.currentIndexChanged.connect(self.update_plan_readiness)
        self.minimum_score = QSpinBox(); self.minimum_score.setRange(0, 100)
        saved_settings = SettingsStore().load()
        self.news_pause = QCheckBox("Emergency News Risk Pause - block all new paper entries")
        self.news_pause.setChecked(bool(saved_settings.get("news_risk_pause", False)))
        self.news_pause.toggled.connect(self.save_news_risk_controls)
        self.event_override = QCheckBox("Override automatic event block for this paper-test session")
        self.event_override.setChecked(bool(saved_settings.get("event_risk_override", False)))
        self.event_override.toggled.connect(self.save_news_risk_controls)
        self.event_window = QComboBox(); self.event_window.addItems(("15 minutes", "30 minutes", "60 minutes"))
        self.event_window.setCurrentText(f"{saved_settings.get('event_no_trade_minutes', 30)} minutes")
        self.event_window.currentIndexChanged.connect(self.save_news_risk_controls)
        self.minimum_score.setValue(int(saved_settings["trade_plan_min_score"]))
        self.minimum_score.setSuffix(" / 100")
        self.minimum_score.setToolTip("0-100 testing threshold for manual review and paper plans. Strict auto paper trading keeps TPS v2 confirmations and hard safety filters.")
        self.minimum_score.valueChanged.connect(self.save_trade_plan_minimum)
        for control in (self.underlying, self.expiry, self.option_type, self.strike, self.lots, self.event_check):
            control.setMinimumHeight(32)
        self.quantity_preview = QLabel("Quantity: load a contract")
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setSingleShot(True)
        self.auto_refresh_timer.timeout.connect(self.refresh_selected_context)
        load = QPushButton("Load Current Expiries")
        load.clicked.connect(self.load_contracts)
        refresh = QPushButton("Refresh & Analyze Selected Contract")
        refresh.clicked.connect(self.refresh_selected_context)
        analyze_chain = QPushButton("Analyze Selected Expiry OI / PCR")
        analyze_chain.clicked.connect(self.load_chain_analysis)
        form.addRow("Underlying", self.underlying)
        form.addRow(load)
        form.addRow("Expiry", self.expiry)
        form.addRow("Type", self.option_type)
        form.addRow("Strike", self.strike)
        form.addRow("Lots (1–100)", self.lots)
        form.addRow("Auto quantity", self.quantity_preview)
        form.addRow("News / event check", self.event_check)
        form.addRow(self.news_pause)
        form.addRow(self.event_override)
        form.addRow("Event no-trade window", self.event_window)
        form.addRow("Testing trade-plan score (0-100)", self.minimum_score)
        form.addRow(refresh)
        form.addRow(analyze_chain)
        layout.addWidget(selection)

        checklist_box = QGroupBox("2. Session checklist - only ticked evidence is scored")
        checklist_form = QFormLayout(checklist_box)
        self.condition_checks = {}
        enabled_conditions = set(saved_settings["tps_enabled_conditions"])
        for name in CONDITION_WEIGHTS:
            check = QCheckBox(name); check.setChecked(name in enabled_conditions)
            check.toggled.connect(self.save_tps_checklist)
            self.condition_checks[name] = check; checklist_form.addRow(check)
        self.match_mode = QComboBox(); self.match_mode.addItem("Adaptive by market regime (recommended)", "adaptive"); self.match_mode.addItem("Selected count", "count"); self.match_mode.addItem("All selected", "all")
        self.match_mode.setCurrentIndex(max(0, self.match_mode.findData(saved_settings["tps_match_mode"])))
        self.match_mode.currentIndexChanged.connect(self.save_tps_checklist)
        self.required_matches = QSpinBox(); self.required_matches.setRange(1, len(CONDITION_WEIGHTS)); self.required_matches.setValue(saved_settings["tps_required_matches"])
        self.required_matches.valueChanged.connect(self.save_tps_checklist)
        checklist_form.addRow("Match rule", self.match_mode); checklist_form.addRow("Required matches", self.required_matches)
        self.side_score_status = QLabel("CE score: waiting | PE score: waiting | Hard blockers: waiting")
        self.side_score_status.setWordWrap(True); checklist_form.addRow(self.side_score_status)
        self.environment_status = QLabel("Market environment: waiting for live 5-minute data and India VIX")
        self.environment_status.setWordWrap(True); checklist_form.addRow(self.environment_status)
        layout.addWidget(checklist_box)

        self.details = QLabel("Load current expiries to choose an option contract.")
        layout.addWidget(self.details)
        self.decision = QLabel("Buying only: CE needs bullish underlying confirmation; PE needs bearish underlying confirmation.\nNaked option selling is intentionally not available in this version.")
        self.decision.setWordWrap(True)
        layout.addWidget(self.decision)
        self.plan_status = QLabel("Trade plan checklist: Chart confirmation required • OI/PCR analysis required")
        self.plan_status.setWordWrap(True)
        layout.addWidget(self.plan_status)
        self.open_chart_button = QPushButton("1. Open Chart Capture & Evaluate")
        self.open_chart_button.clicked.connect(self.open_chart_capture.emit)
        layout.addWidget(self.open_chart_button)
        self.create_plan_button = QPushButton("Create Review Trade Plan (Auto-select CE / PE)")
        self.create_plan_button.clicked.connect(self.create_trade_plan)
        self.create_plan_button.setEnabled(False)
        layout.addWidget(self.create_plan_button)
        self.paper_button = QPushButton("Capture Paper Trade (ATM, 1 Lot - no broker order)")
        self.paper_button.clicked.connect(self.capture_paper_trade)
        self.paper_button.setEnabled(False)
        layout.addWidget(self.paper_button)
        auto_box = QGroupBox("Auto Paper Trading - selected checklist + score + hard-risk validation")
        auto_form = QFormLayout(auto_box)
        self.auto_paper_enabled = QCheckBox("Enable configurable auto paper trades (ATM, 1 lot, no real order)")
        self.auto_paper_enabled.toggled.connect(self.set_auto_paper_enabled)
        self.auto_paper_progress = QLabel("Disabled. This mode only evaluates each completed 5-minute candle during market hours.")
        self.auto_paper_progress.setWordWrap(True)
        auto_form.addRow(self.auto_paper_enabled)
        auto_form.addRow(self.auto_paper_progress)
        layout.addWidget(auto_box)
        self.send_plan_button = QPushButton("Send Review Plan to Journal")
        self.send_plan_button.clicked.connect(self.send_plan_to_journal)
        self.send_plan_button.setEnabled(False)
        layout.addWidget(self.send_plan_button)
        layout.addWidget(QLabel("TPS only analyses data. It does not place, modify, or cancel a broker order."))
        layout.addStretch()
        self.contracts_loaded.connect(self.show_contracts)
        self.load_error.connect(self.show_error)
        self.quote_loaded.connect(self.show_quote)
        self.quote_error.connect(self.show_error)
        self.chain_loaded.connect(self.show_chain_analysis)
        self.chain_error.connect(self.show_error)
        self.paper_trade_captured.connect(self.show_paper_trade_captured)
        self.paper_trade_closed.connect(self.show_paper_trade_closed)
        self.paper_trade_monitored.connect(self.show_paper_trade_monitoring)
        self.paper_trade_error.connect(self.show_paper_trade_error)
        self.auto_paper_status.connect(self.show_auto_paper_status)
        self.auto_paper_captured.connect(self.show_auto_paper_captured)
        self.paper_monitor_timer = QTimer(self)
        self.paper_monitor_timer.timeout.connect(self.monitor_paper_trades)
        self.auto_paper_timer = QTimer(self)
        self.auto_paper_timer.timeout.connect(self.check_auto_paper_cycle)

    def load_contracts(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Broker", "Connect live data from Settings first so TPS can use the current spot price.")
            return
        self.details.setText("Downloading today's instrument master…")
        Thread(target=self._load_contracts, args=(self.underlying.currentText(),), daemon=True).start()

    def _load_contracts(self, underlying):
        try:
            contracts = self.service.get_contracts(underlying)
            quote_config = UNDERLYING_QUOTES[underlying]
            quote = LiveSession.client.get_option_quote(quote_config["exchange"], quote_config["token"])
            spot_price = float(quote.get("ltp", 0) or 0)
            if spot_price <= 0:
                raise RuntimeError("The connected broker did not return a usable spot price.")
            focused = contracts_near_spot(contracts, spot_price, wings=5)
            self.contracts_loaded.emit({"contracts": focused, "spot_price": spot_price})
        except (RuntimeError, ValueError) as error:
            self.load_error.emit(str(error))

    def show_contracts(self, result):
        self.contracts = result["contracts"]
        self.spot_price = result["spot_price"]
        self.chain_context = None
        self.current_plan = None
        self.send_plan_button.setEnabled(False)
        self.update_plan_readiness()
        self.expiry.blockSignals(True)
        self.expiry.clear()
        for expiry in sorted({contract["expiry"] for contract in self.contracts}):
            self.expiry.addItem(expiry.strftime("%d %b %Y"), expiry)
        self.expiry.blockSignals(False)
        self.populate_strikes()
        self.details.setText(
            f"Live Angel spot: {result['spot_price']:,.2f}. {len(self.contracts)} focused contracts loaded. "
            "Nearest current-expiry ATM strike is selected automatically; change it manually if required."
        )
        self.schedule_auto_refresh()

    def populate_strikes(self):
        if not self.contracts or self.expiry.currentIndex() < 0:
            return
        expiry = self.expiry.currentData()
        option_type = self.option_type.currentText()
        selected = [contract for contract in self.contracts if contract["expiry"] == expiry and contract["option_type"] == option_type]
        self.strike.clear()
        for contract in selected:
            self.strike.addItem(f"{contract['strike']:,.0f}", contract)
        if selected and self.spot_price is not None:
            atm_index = min(range(len(selected)), key=lambda index: abs(float(selected[index]["strike"]) - self.spot_price))
            self.strike.setCurrentIndex(atm_index)

    def selected_contract(self):
        contract = self.strike.currentData()
        if not contract:
            raise ValueError("Load expiries and select a valid option contract first.")
        return contract

    def update_lot_quantity(self, *_args):
        contract = self.strike.currentData()
        if not contract:
            self.quantity_preview.setText("Quantity: load a contract")
            return
        lot_size = int(contract.get("lot_size", 0) or 0)
        self.quantity_preview.setText(f"{self.lots.value()} lot(s) × {lot_size} = {self.lots.value() * lot_size} quantity")

    def load_quote(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Broker", "Connect live data from Settings first.")
            return
        try:
            contract = self.selected_contract()
        except ValueError as error:
            QMessageBox.warning(self, "Option contract", str(error))
            return
        self.details.setText("Refreshing live option quote…")
        Thread(target=self._load_quote, args=(contract,), daemon=True).start()

    def schedule_auto_refresh(self, *_args):
        """Coalesce rapid selector changes into one read-only batch quote request."""
        if self.contracts and self.expiry.currentIndex() >= 0 and self.strike.currentIndex() >= 0:
            self.auto_refresh_timer.start(450)

    def refresh_selected_context(self):
        if not LiveSession.connected() or not self.contracts or self.expiry.currentIndex() < 0:
            return
        if self.chain_loading:
            self.auto_refresh_pending = True
            return
        expiry = self.expiry.currentData()
        contracts = [contract for contract in self.contracts if contract["expiry"] == expiry]
        if self.chain_loading:
            self.auto_refresh_pending = True
            return
        self.chain_loading = True
        if not contracts:
            return
        self.chain_loading = True
        self.details.setText("Auto-refreshing selected contract and focused OI / PCR...")
        Thread(target=self._load_chain_analysis, args=(contracts, self.underlying.currentText()), daemon=True).start()

    def _load_quote(self, contract):
        try:
            quote = LiveSession.client.get_option_quote(contract["exchange"], contract["token"])
            self.quote_loaded.emit({"contract": contract, "quote": quote})
        except RuntimeError as error:
            self.quote_error.emit(str(error))

    def show_quote(self, result):
        contract, quote = result["contract"], result["quote"]
        premium = float(quote.get("ltp", 0) or 0)
        settings = SettingsStore().load()
        risk = buying_risk(premium, contract["lot_size"], settings["capital"], settings["risk_percent"])
        oi = quote.get("opnInterest", "—")
        volume = quote.get("tradeVolume", "—")
        greeks = calculate_greeks(self.spot_price, contract["strike"], premium, contract.get("expiry"), contract["option_type"]) if self.spot_price else None
        greek_text = (
            f"\nModel Greeks (estimate): IV {greeks['iv']:.2f}% | Delta {greeks['delta']:.3f} | Theta/day {greeks['theta_per_day']:.2f} | Gamma {greeks['gamma']:.5f}"
            if greeks else "\nModel Greeks unavailable: verify premium, expiry and liquidity; TPS will not invent values."
        )
        self.details.setText(
            f"{contract['symbol']}\nPremium: ₹{premium:,.2f} | OI: {oi} | Volume: {volume}\n"
            f"Lot size: {contract['lot_size']} | One-lot premium risk: ₹{risk['per_lot_risk']:,.2f}\n"
            f"Your configured risk cap: ₹{risk['risk_cap']:,.2f} | Whole lots within cap: {risk['lots']}{greek_text}"
        )
        expected = "bullish" if contract["option_type"] == "CE" else "bearish"
        self.decision.setText(
            f"{contract['option_type']} buying checklist: underlying must show {expected} structure, "
            "a confirmed 5m breakout/breakdown, and adequate option volume.\n"
            "If any condition is missing or lots within your risk cap are 0: avoid the entry."
        )

    def load_chain_analysis(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Broker", "Connect live data from Settings first.")
            return
        if not self.contracts or self.expiry.currentIndex() < 0:
            QMessageBox.warning(self, "Options", "Load current expiries first.")
            return
        expiry = self.expiry.currentData()
        contracts = [contract for contract in self.contracts if contract["expiry"] == expiry]
        self.details.setText("Refreshing focused option-chain OI and PCR…")
        Thread(target=self._load_chain_analysis, args=(contracts, self.underlying.currentText()), daemon=True).start()

    def _load_chain_analysis(self, contracts, underlying):
        try:
            quotes = LiveSession.client.get_option_chain_quotes(contracts[0]["exchange"], [contract["token"] for contract in contracts])
            analysis = analyze_option_chain(contracts, quotes)
            try:
                pcr_records = LiveSession.client.get_put_call_ratios()
                official_pcr = next((record.get("pcr") for record in pcr_records if str(record.get("tradingSymbol", "")).upper().startswith(underlying.upper())), None)
            except RuntimeError:
                official_pcr = None
            analysis["official_pcr"] = official_pcr
            analysis["underlying"] = underlying
            self.chain_loaded.emit(analysis)
        except (RuntimeError, ValueError) as error:
            self.chain_error.emit(str(error))

    def show_chain_analysis(self, analysis):
        self.chain_loading = False
        analysis["expiry"] = self.expiry.currentData()
        self.chain_context = analysis
        self.update_plan_readiness()
        def number(value):
            return f"{float(value):.2f}" if value is not None else "unavailable"
        selected = self.strike.currentData()
        selected_row = next((row for row in analysis["quote_rows"] if selected and row["token"] == selected["token"]), None)
        selected_text = "Selected contract quote unavailable"
        if selected_row:
            selected_text = (
                f"Selected {selected_row['symbol']} | Premium: ₹{selected_row['ltp']:,.2f}"
                f" | OI: {selected_row['oi']:,.0f} | Volume: {selected_row['volume']:,.0f}"
            )
            greeks = calculate_greeks(self.spot_price, selected["strike"], selected_row["ltp"], selected.get("expiry"), selected["option_type"])
            if greeks:
                selected_text += f" | Greeks est. IV {greeks['iv']:.1f}% Δ {greeks['delta']:.3f} Θ/day {greeks['theta_per_day']:.2f}"
            else:
                selected_text += " | Greeks unavailable (no estimate created)"
        self.details.setText(
            f"{selected_text}\n"
            f"Focused expiry analysis ({analysis['quoted_contracts']}/{analysis['total_contracts']} contracts quoted)\n"
            f"Focused OI PCR: {number(analysis['pcr_oi'])} | Focused volume PCR: {number(analysis['pcr_volume'])}\n"
            f"Broker market PCR: {number(analysis['official_pcr'])}\n"
            f"Put-OI support zone: {analysis['put_support'] or 'unavailable'} | "
            f"Call-OI resistance zone: {analysis['call_resistance'] or 'unavailable'}\n"
            f"Context: {analysis['context']}"
        )
        self.decision.setText(
            "Use OI/PCR as context, not a standalone signal. Take a CE/PE decision only when the live underlying "
            "structure, breakout/breakdown, option liquidity, and risk-limit checks all agree."
        )
        if self.auto_refresh_pending:
            self.auto_refresh_pending = False
            self.schedule_auto_refresh()

    def set_chart_context(self, context: dict):
        """Receive the last explicit Decision Engine evaluation for plan gating."""
        self.chart_context = context
        symbol = context.get("symbol") or "unknown symbol"
        self.decision.setText(
            f"Chart evaluation received for {symbol}: {context['decision']} ({context['score']}/100). "
            "Run expiry OI/PCR analysis, then create a review plan."
        )
        self.update_plan_readiness()

    def update_plan_readiness(self):
        underlying = self.underlying.currentText()
        minimum_score = self.minimum_score.value()
        chart_ready = bool(
            self.chart_context
            and self.chart_context.get("symbol") == underlying
            and self.chart_context.get("score", 0) >= minimum_score
            and bool(self.chart_context.get("volume_confirmed"))
            and self.chart_context.get("direction") in {"BULLISH", "BEARISH"}
        )
        chain_ready = bool(self.chain_context and self.chain_context.get("underlying") == underlying)
        chart_text = "✓ Fresh STRONG chart confirmation" if chart_ready else "• Fresh STRONG chart confirmation required"
        chain_text = "✓ OI/PCR analysis ready" if chain_ready else "• Selected-expiry OI/PCR analysis required"
        self.plan_status.setText(f"Trade plan checklist: {chart_text}  |  {chain_text}")
        score = self.chart_context.get("score") if self.chart_context else None
        score_text = f"Trade Plan Score: {score}/100" if score is not None else "Trade Plan Score: waiting for chart"
        chart_text = "✓ Score above 75" if chart_ready else "• Score above 75 required"
        chain_text = "✓ OI/PCR analysis ready" if chain_ready else "• Selected-expiry OI/PCR analysis required"
        open_trade = self.db.has_open_trade(underlying)
        expiry_day = self.expiry.currentData() == date.today()
        event_ready = self.event_check.currentText() == "No known high-impact event" and not expiry_day and not self.news_pause.isChecked()
        event_text = "⚠ Expiry-day caution: TPS blocks new plans; review manually" if expiry_day else (
            "✓ News/event check recorded" if event_ready else "• Confirm no high-impact news/event before planning"
        )
        if self.news_pause.isChecked():
            event_text = "[BLOCK] Emergency News Risk Pause is ON"
        open_text = "[!] Close/review the active open trade before a new plan" if open_trade else "[OK] No active open trade for this underlying"
        self.plan_status.setText(
            f"{score_text} (minimum: {minimum_score})  |  "
            f"{'✓ Configured score and high-volume confirmation met' if chart_ready else f'• Score {minimum_score}+ and Volume > Volume EMA 20 required'}  |  "
            f"{chain_text}  |  {event_text}  |  {open_text}"
        )
        if minimum_score < 50:
            self.plan_status.setText(
                self.plan_status.text() +
                "  |  [TEST MODE] Low score does not bypass volume, direction, OI, event, or open-trade safety checks."
            )
        ready = chart_ready and chain_ready and event_ready and not open_trade
        self.create_plan_button.setEnabled(ready)
        self.paper_button.setEnabled(ready)

    def save_trade_plan_minimum(self, value):
        settings = SettingsStore().load()
        settings["trade_plan_min_score"] = int(value)
        SettingsStore().save(settings)
        self.current_plan = None
        self.send_plan_button.setEnabled(False)
        self.update_plan_readiness()

    def save_tps_checklist(self, *_args):
        enabled = [name for name, check in self.condition_checks.items() if check.isChecked()]
        if not enabled:
            sender = self.sender()
            if isinstance(sender, QCheckBox):
                sender.blockSignals(True); sender.setChecked(True); sender.blockSignals(False)
                enabled = [sender.text()]
        self.required_matches.setMaximum(max(1, len(enabled)))
        if self.required_matches.value() > len(enabled):
            self.required_matches.setValue(len(enabled))
        settings = SettingsStore().load()
        settings.update({
            "tps_enabled_conditions": enabled,
            "tps_match_mode": self.match_mode.currentData(),
            "tps_required_matches": self.required_matches.value(),
        })
        SettingsStore().save(settings)
        self.update_plan_readiness()

    def save_news_risk_controls(self, *_args):
        settings = SettingsStore().load()
        settings["news_risk_pause"] = self.news_pause.isChecked()
        settings["event_risk_override"] = self.event_override.isChecked()
        settings["event_no_trade_minutes"] = int(self.event_window.currentText().split()[0])
        SettingsStore().save(settings)
        if self.news_pause.isChecked() and self.auto_paper_enabled.isChecked():
            self.auto_paper_enabled.setChecked(False)
        self.update_plan_readiness()

    def prepare_live_workspace(self):
        """Open with current expiry/ATM data already loading when a live session exists."""
        if LiveSession.connected() and not self.contracts:
            self.load_contracts()
        if LiveSession.connected() and not self.paper_monitor_timer.isActive():
            self.paper_monitor_timer.start(30_000)
            self.monitor_paper_trades()

    def create_trade_plan(self):
        if not self.contracts or self.spot_price is None:
            QMessageBox.warning(self, "Trade plan", "Load current expiries first.")
            return
        expiry = self.expiry.currentData()
        if not self.chain_context or self.chain_context.get("expiry") != expiry:
            QMessageBox.warning(self, "Trade plan", "Run OI / PCR analysis for the selected expiry first.")
            return
        contracts = [contract for contract in self.contracts if contract["expiry"] == expiry]
        try:
            plan = create_review_plan(
                self.underlying.currentText(), self.spot_price, contracts,
                self.chain_context["quote_rows"], self.chart_context, self.chain_context, SettingsStore().load(),
                requested_lots=self.lots.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Trade plan", str(error))
            return
        self.current_plan = plan
        self.option_type.setCurrentText(plan["option_type"])
        self.populate_strikes()
        for index in range(self.strike.count()):
            candidate = self.strike.itemData(index)
            if candidate and candidate["token"] == plan["contract"]["token"]:
                self.strike.setCurrentIndex(index)
                break
        self.decision.setText(
            f"REVIEW PLAN — {plan['contract']['symbol']}\n"
            f"Entry reference: ₹{plan['entry']:,.2f} | Stop: ₹{plan['stoploss']:,.2f} | Target: ₹{plan['target']:,.2f}\n"
            f"Underlying regular-move objective: {plan.get('underlying_target') or '-'} "
            f"({plan.get('underlying_target_points') or '-'} points)\n"
            f"Quantity: {plan['quantity']} ({plan['lots']} lot(s) × {plan['lot_size']})\n"
            + "\n".join(f"• {reason}" for reason in plan["reasons"]) + f"\n\n{plan['warning']}"
        )
        self.send_plan_button.setEnabled(True)

    def capture_paper_trade(self):
        """Create a one-lot paper position and begin quote-only monitoring."""
        if not self.contracts or self.spot_price is None or not self.chain_context:
            QMessageBox.warning(self, "Paper trade", "Load the ATM expiry and complete chart plus OI/PCR checks first.")
            return
        expiry = self.expiry.currentData()
        if self.chain_context.get("expiry") != expiry:
            QMessageBox.warning(self, "Paper trade", "Refresh the selected expiry OI/PCR data first.")
            return
        try:
            settings = SettingsStore().load()
            database = Database()
            try:
                recovery = OvertradingGuard().assess(settings, database)
            finally:
                database.close()
            if not recovery["allowed"]:
                QMessageBox.warning(
                    self, "Recovery Mode",
                    "Paper capture blocked:\n\n" + "\n".join(f"• {item}" for item in recovery["blockers"])
                    + "\n\nOpen Overtrading Protection Center to complete today's check-in."
                )
                return
            contracts = [contract for contract in self.contracts if contract["expiry"] == expiry]
            plan = create_review_plan(
                self.underlying.currentText(), self.spot_price, contracts, self.chain_context["quote_rows"],
                self.chart_context, self.chain_context, settings, requested_lots=1,
            )
            database = Database()
            try:
                trade_id = database.save_paper_trade(plan)
            finally:
                database.close()
            plan["trade_id"] = trade_id
            self.paper_trade_captured.emit(plan)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Paper trade", str(error))

    def show_paper_trade_captured(self, plan):
        self.details.setText(
            f"PAPER TRADE CAPTURED - no broker order was sent.\n{plan['contract']['symbol']} | ATM / 1 lot | "
            f"Entry {plan['entry']:.2f} | Stop {plan['stoploss']:.2f} | Target {plan['target']:.2f}.\n"
            "TPS will check the live option LTP every 30 seconds and book the first hit in the Trade Journal."
        )
        if not self.paper_monitor_timer.isActive():
            self.paper_monitor_timer.start(30_000)
        self.update_plan_readiness()

    def monitor_paper_trades(self):
        if self.paper_monitoring or not LiveSession.connected():
            return
        self.paper_monitoring = True
        Thread(target=self._monitor_paper_trades, daemon=True).start()

    def _monitor_paper_trades(self):
        database = Database()
        try:
            closed = database.monitor_paper_trades(LiveSession.client, SettingsStore().load())
            monitoring = database.get_paper_trade_monitoring()
            if closed:
                self.paper_trade_closed.emit(closed)
            elif monitoring:
                self.paper_trade_monitored.emit(monitoring)
        except (RuntimeError, ValueError) as error:
            self.paper_trade_error.emit(str(error))
        finally:
            database.close()
            self.paper_monitoring = False

    def show_paper_trade_closed(self, closed):
        summary = "; ".join(f"{item['symbol']} {item['outcome']} at {item['ltp']:.2f}" for item in closed)
        self.details.setText(f"PAPER TRADE AUTO-BOOKED: {summary}. It has been saved in Trade Journal; review the result before using any real-money plan.")
        self.update_plan_readiness()

    def show_paper_trade_monitoring(self, rows):
        lines = []
        for row in rows:
            alert = f" | {row['alert']} STOP WARNING" if row.get("alert") else ""
            lines.append(
                f"{row['symbol']} LTP {row.get('ltp') or 0:.2f} | SL {row['stoploss']:.2f} | "
                f"Target {row['target']:.2f} | MAE {row['mae']:.2f} | MFE {row['mfe']:.2f}{alert}"
            )
        self.details.setText("PAPER TRADE PREMIUM MONITOR (30-second quote check)\n" + "\n".join(lines))

    def show_paper_trade_error(self, message):
        self.details.setText(f"Paper-trade monitor paused: {message}. No broker order was sent; retry after broker data is available.")

    def set_auto_paper_enabled(self, enabled: bool):
        if enabled:
            if self.news_pause.isChecked():
                self.auto_paper_enabled.blockSignals(True); self.auto_paper_enabled.setChecked(False); self.auto_paper_enabled.blockSignals(False)
                QMessageBox.warning(self, "Auto paper trading", "Emergency News Risk Pause is ON. Turn it off only after reviewing event risk.")
                return
            if self.event_check.currentText() != "No known high-impact event":
                self.auto_paper_enabled.blockSignals(True); self.auto_paper_enabled.setChecked(False); self.auto_paper_enabled.blockSignals(False)
                QMessageBox.warning(self, "Auto paper trading", "First select 'No known high-impact event' after checking news/events. TPS will not automate around an unreviewed event.")
                return
            if not LiveSession.connected():
                self.auto_paper_enabled.blockSignals(True); self.auto_paper_enabled.setChecked(False); self.auto_paper_enabled.blockSignals(False)
                QMessageBox.warning(self, "Auto paper trading", "Connect read-only broker data first.")
                return
            self.auto_paper_progress.setText("Enabled: waits for each new completed 5-minute candle. One open paper trade at a time; daily cap comes from Risk Settings.")
            self.auto_paper_timer.start(30_000)
            self.check_auto_paper_cycle()
        else:
            self.auto_paper_timer.stop()
            self.auto_paper_progress.setText("Paused. Existing open paper trades remain quote-monitored; no new paper trade will be captured.")

    def check_auto_paper_cycle(self):
        if not self.auto_paper_enabled.isChecked() or self.auto_paper_running or not LiveSession.connected():
            return
        now = datetime.now().astimezone()
        market_open = now.weekday() < 5 and ((now.hour == 9 and now.minute >= 15) or 10 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30))
        if not market_open:
            self.auto_paper_status.emit("Auto paper mode is waiting for NSE market hours (09:15-15:30).")
            return
        bucket_start = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        bucket = bucket_start.isoformat()
        if bucket == self.last_auto_paper_bucket:
            return
        self.auto_paper_running = True
        settings = SettingsStore().load()
        mode = "adaptive market regime" if settings["tps_match_mode"] == "adaptive" else "all selected" if settings["tps_match_mode"] == "all" else f"{settings['tps_required_matches']} matches"
        self.auto_paper_status.emit(
            f"Checking completed 5-minute candle independently for CE and PE: {mode}, "
            f"score {settings['trade_plan_min_score']}+, then hard-risk blockers..."
        )
        Thread(target=self._run_auto_paper_cycle, args=(self.underlying.currentText(), bucket, bucket_start), daemon=True).start()

    def _run_auto_paper_cycle(self, symbol, bucket, bucket_start):
        try:
            result = run_auto_paper_cycle(LiveSession.client, symbol, SettingsStore().load())
            self.last_auto_paper_bucket = bucket
            self.auto_attempt_saved.emit()
            if result.get("plan"):
                self.auto_paper_captured.emit(result)
            else:
                self.auto_paper_status.emit(result)
        except (RuntimeError, ValueError) as error:
            candle_time = (bucket_start - timedelta(minutes=5)).isoformat()
            result = {
                "status": f"Retry pending for candle {candle_time}: {error} TPS will retry this same candle automatically.",
                "retry_pending": True,
                "attempt": {"checked_at": datetime.now().astimezone().isoformat(timespec="seconds"), "candle_time": candle_time, "future_symbol": None, "candidate": None, "capture": {}, "chart": {}, "chain": {}, "blockers": [str(error), "Automatic retry remains pending for this candle"]},
            }
            database = Database()
            try:
                database.save_auto_trade_attempt(symbol, result)
            finally:
                database.close()
            self.auto_attempt_saved.emit()
            self.auto_paper_status.emit(result)
        finally:
            self.auto_paper_running = False

    @staticmethod
    def format_auto_paper_attempt(result):
        if isinstance(result, str):
            return result
        attempt = result.get("attempt") or {}
        capture = attempt.get("capture") or {}
        chart = attempt.get("chart") or {}
        lines = [result.get("status", "Auto paper cycle completed.")]
        lines.append(f"Checked at: {attempt.get('checked_at') or 'Unavailable'} | Candle time: {attempt.get('candle_time') or 'Not evaluated'} | Future: {attempt.get('future_symbol') or 'Not loaded'}")
        if capture:
            lines.extend((
                f"OHLC: O {capture.get('open', '-')} | H {capture.get('high', '-')} | L {capture.get('low', '-')} | C {capture.get('close', '-')}",
                f"Trend values: EMA 5 {capture.get('ema_5', '-')} | EMA 20 {capture.get('ema_20', '-')} | EMA 50 {capture.get('ema_50', '-')} | VWAP {capture.get('vwap', '-')} | SuperTrend {capture.get('supertrend', '-')} ({capture.get('supertrend_state', '-')})",
                f"Momentum: RSI 14 {capture.get('rsi_14', '-')} | ATR 14 {capture.get('atr_14', '-')} | Candle {capture.get('candle_direction', '-')}",
                f"Volume: {capture.get('volume', '-')} | Volume EMA 20: {capture.get('volume_ema', '-')} | Ratio: {capture.get('volume_ratio', '-')}x | {capture.get('volume_signal', '-')}",
            ))
        if chart:
            strategy = chart.get("strategy") or {}
            sides = strategy.get("side_evaluations") or {}
            ce, pe = sides.get("CE") or {}, sides.get("PE") or {}
            lines.append(
                f"Decision: {chart.get('decision', '-')} | Candidate: {attempt.get('candidate') or '-'} | "
                f"CE {ce.get('passed', '-')}/{ce.get('total', '-')} score {ce.get('score', '-')} | "
                f"PE {pe.get('passed', '-')}/{pe.get('total', '-')} score {pe.get('score', '-')} | "
                f"Required {strategy.get('required', '-')} matches + {strategy.get('minimum_score', '-')} score | "
                f"{strategy.get('required_reason', strategy.get('match_mode', '-'))}"
            )
            confirmations = strategy.get("confirmations") or []
            if confirmations:
                lines.append("Selected-side checklist evidence:")
                lines.extend(f"{'PASS' if item['passed'] else 'FAIL'} — {item['name']}: {item['detail']}" for item in confirmations)
            zones = strategy.get("zones") or {}
            if zones:
                lines.append(
                    f"Zone confluence: Chart support {zones.get('chart_support', '-')} vs Put-OI support {zones.get('oi_support', '-')} "
                    f"({'MATCH' if zones.get('support_confluence') else 'NOT ALIGNED'}) | Chart resistance {zones.get('chart_resistance', '-')} "
                    f"vs Call-OI resistance {zones.get('oi_resistance', '-')} ({'MATCH' if zones.get('resistance_confluence') else 'NOT ALIGNED'}) | "
                    f"Tolerance {zones.get('tolerance', '-')}"
                )
            selected_side = sides.get(attempt.get("candidate")) or {}
            entry_quality = selected_side.get("entry_quality") or {}
            if entry_quality:
                lines.append(
                    f"Entry timing: {'TIMELY' if entry_quality.get('timely') else 'LATE / EXTENDED'} | "
                    f"Distance {entry_quality.get('extension_points')} points = {entry_quality.get('extension_atr')} ATR "
                    f"(maximum {entry_quality.get('maximum_extension_atr')} ATR) | RSI {entry_quality.get('rsi')} | "
                    f"Fresh pullback/reversal {'YES' if entry_quality.get('fresh_pullback_reversal') else 'NO'}"
                )
            reasons = chart.get("reasons") or []
            if reasons:
                lines.append("Conditions passed: " + "; ".join(reasons))
            environment = strategy.get("market_environment") or chart.get("market_environment") or {}
            if environment:
                lines.append(
                    f"Environment: {environment.get('regime')} | India VIX {environment.get('vix') or 'Unavailable'} "
                    f"({environment.get('vix_zone')}) | ATR {environment.get('atr_percent')}% | "
                    f"Risk multiplier {environment.get('risk_multiplier')}"
                )
                event = environment.get("event_risk") or {}
                lines.append(
                    f"Opening range {environment.get('opening_range_low')} - {environment.get('opening_range_high')} | "
                    f"Previous day H/L {environment.get('previous_day_high')} / {environment.get('previous_day_low')} | "
                    f"{environment.get('gap_state')} {environment.get('gap_points')} | Event {event.get('status', 'Unavailable')}"
                )
                lines.append(
                    f"VIX range budget: expected {environment.get('expected_daily_range')} | used {environment.get('session_range')} "
                    f"({environment.get('range_consumed_percent')}%) | remaining {environment.get('remaining_expected_range')} | "
                    f"regular objective {environment.get('regular_move_target_points')} points | "
                    f"adaptive extension {environment.get('max_entry_extension_atr')} ATR"
                )
                for item in event.get("nearby_events", [])[:5]:
                    lines.append(
                        f"Economic event: {item.get('name')} | {item.get('country')} | {item.get('time')} | "
                        f"Impact {item.get('importance')} | Forecast {item.get('forecast') or '-'} | "
                        f"Actual {item.get('actual') or '-'} | Previous {item.get('previous') or '-'} | "
                        f"{item.get('minutes_from_now')} minute(s) from check"
                    )
                expiry_strategy = environment.get("expiry_strategy") or {}
                if expiry_strategy:
                    lines.append(f"Expiry strategy: {expiry_strategy.get('strategy')} | {expiry_strategy.get('reason')}")
        chain = attempt.get("chain") or {}
        if chain:
            oi_pcr = f"{chain['pcr_oi']:.2f}" if chain.get("pcr_oi") is not None else "Unavailable"
            volume_pcr = f"{chain['pcr_volume']:.2f}" if chain.get("pcr_volume") is not None else "Unavailable"
            lines.append(f"Option chain: OI PCR {oi_pcr} | Volume PCR {volume_pcr} | Put support {chain.get('put_support', '-')} | Call resistance {chain.get('call_resistance', '-')} | {chain.get('context', '')}")
        blockers = attempt.get("blockers") or []
        lines.append("Why trade was not captured: " + ("; ".join(dict.fromkeys(blockers)) if blockers else "All strict conditions passed; paper trade was captured."))
        return "\n".join(lines)

    def show_auto_paper_status(self, result):
        progress = self.db.paper_trade_progress()
        details = self.format_auto_paper_attempt(result)
        if isinstance(result, dict):
            strategy = (((result.get("attempt") or {}).get("chart") or {}).get("strategy") or {})
            sides = strategy.get("side_evaluations") or {}
            ce, pe = sides.get("CE") or {}, sides.get("PE") or {}
            blockers = strategy.get("hard_blockers") or []
            if sides:
                self.side_score_status.setText(
                    f"CE: {ce.get('score', 0)}/100 ({ce.get('passed', 0)}/{ce.get('total', 0)}) {ce.get('state', '')} | "
                    f"PE: {pe.get('score', 0)}/100 ({pe.get('passed', 0)}/{pe.get('total', 0)}) {pe.get('state', '')}\n"
                    f"Hard blockers for selected side: {'; '.join(blockers) if blockers else 'None'}"
                )
            environment = strategy.get("market_environment") or {}
            if environment:
                expected = environment.get("expected_daily_range")
                self.environment_status.setText(
                    f"Market environment: {environment.get('regime')} | India VIX {environment.get('vix') or 'Unavailable'} "
                    f"({environment.get('vix_zone')}) | Expected daily range "
                    f"{'±' + format(expected, ',.2f') if expected is not None else 'Unavailable'} | "
                    f"Risk quantity {environment.get('risk_multiplier', 1) * 100:.0f}% | {environment.get('strike_preference')}\n"
                    f"Opening range {environment.get('opening_range_low')}–{environment.get('opening_range_high')} | "
                    f"Previous day H/L {environment.get('previous_day_high')}/{environment.get('previous_day_low')} | "
                    f"{environment.get('gap_state')} {environment.get('gap_points')} | "
                    f"Event {(environment.get('event_risk') or {}).get('status', 'Unavailable')} | "
                    f"{(environment.get('expiry_strategy') or {}).get('strategy', environment.get('strategy_preference', 'Directional'))}\n"
                    f"Range used {environment.get('session_range')} ({environment.get('range_consumed_percent')}%) | "
                    f"Remaining {environment.get('remaining_expected_range')} | Regular objective "
                    f"{environment.get('regular_move_target_points')} points | Entry extension max "
                    f"{environment.get('max_entry_extension_atr')} ATR"
                )
        self.auto_paper_progress.setText(f"{details}\nForward-test progress: {progress['days']}/20 trading days | {progress['trades']} paper trades | {progress['target_hits']} targets | {progress['stoploss_hits']} stop losses.")

    def show_auto_paper_captured(self, result):
        plan = result["plan"]
        progress = self.db.paper_trade_progress()
        self.auto_paper_progress.setText(
            f"PAPER TRADE #{result['trade_id']} captured: {plan['contract']['symbol']} | 1 lot / {plan['quantity']} qty | "
            f"Entry {plan['entry']:.2f}, Stop {plan['stoploss']:.2f}, Target {plan['target']:.2f}. Live quote monitoring is active.\n"
            f"{self.format_auto_paper_attempt(result)}\n"
            f"Forward-test progress: {progress['days']}/20 trading days | {progress['trades']} paper trades."
        )
        self.paper_trade_captured.emit(plan)
        if not self.paper_monitor_timer.isActive():
            self.paper_monitor_timer.start(30_000)
        self.update_plan_readiness()

    def send_plan_to_journal(self):
        if not self.current_plan:
            return
        self.trade_plan_ready.emit(self.current_plan)

    def show_error(self, message):
        self.chain_loading = False
        self.auto_refresh_pending = False
        self.details.setText(f"Options data unavailable: {message}")
