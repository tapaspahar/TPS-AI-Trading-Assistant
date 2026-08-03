from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
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

    def __init__(self):
        super().__init__()
        self.contracts = []
        self.spot_price = None
        self.chart_context = None
        self.chain_context = None
        self.current_plan = None
        self.chain_loading = False
        self.auto_refresh_pending = False
        self.service = OptionContractService()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Options Decision Workspace — verify every condition before placing a manual broker order."))

        selection = QGroupBox("1. Choose a contract")
        form = QFormLayout(selection)
        self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.underlying.currentTextChanged.connect(lambda _symbol: self.update_plan_readiness())
        self.expiry = QComboBox(); self.expiry.currentIndexChanged.connect(self.populate_strikes)
        self.option_type = QComboBox(); self.option_type.addItems(("CE", "PE")); self.option_type.currentIndexChanged.connect(self.populate_strikes)
        self.strike = QComboBox(); self.strike.currentIndexChanged.connect(self.schedule_auto_refresh)
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
        form.addRow(refresh)
        form.addRow(analyze_chain)
        layout.addWidget(selection)

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
        self.send_plan_button = QPushButton("Send Review Plan to Journal")
        self.send_plan_button.clicked.connect(self.send_plan_to_journal)
        self.send_plan_button.setEnabled(False)
        layout.addWidget(self.send_plan_button)
        layout.addWidget(QLabel("TPS only analyses data. It does not place, modify, or cancel an Angel One order."))
        layout.addStretch()
        self.contracts_loaded.connect(self.show_contracts)
        self.load_error.connect(self.show_error)
        self.quote_loaded.connect(self.show_quote)
        self.quote_error.connect(self.show_error)
        self.chain_loaded.connect(self.show_chain_analysis)
        self.chain_error.connect(self.show_error)

    def load_contracts(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect live data from Settings first so TPS can use the current spot price.")
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
                raise RuntimeError("Angel One did not return a usable spot price.")
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

    def load_quote(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect live data from Settings first.")
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
        self.details.setText(
            f"{contract['symbol']}\nPremium: ₹{premium:,.2f} | OI: {oi} | Volume: {volume}\n"
            f"Lot size: {contract['lot_size']} | One-lot premium risk: ₹{risk['per_lot_risk']:,.2f}\n"
            f"Your configured risk cap: ₹{risk['risk_cap']:,.2f} | Whole lots within cap: {risk['lots']}"
        )
        expected = "bullish" if contract["option_type"] == "CE" else "bearish"
        self.decision.setText(
            f"{contract['option_type']} buying checklist: underlying must show {expected} structure, "
            "a confirmed 5m breakout/breakdown, and adequate option volume.\n"
            "If any condition is missing or lots within your risk cap are 0: avoid the entry."
        )

    def load_chain_analysis(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect live data from Settings first.")
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
        self.details.setText(
            f"{selected_text}\n"
            f"Focused expiry analysis ({analysis['quoted_contracts']}/{analysis['total_contracts']} contracts quoted)\n"
            f"Focused OI PCR: {number(analysis['pcr_oi'])} | Focused volume PCR: {number(analysis['pcr_volume'])}\n"
            f"Angel One market PCR: {number(analysis['official_pcr'])}\n"
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
        chart_ready = bool(
            self.chart_context
            and self.chart_context.get("symbol") == underlying
            and self.chart_context.get("score", 0) > 75
            and str(self.chart_context.get("decision", "")) != "NO TRADE"
        )
        chain_ready = bool(self.chain_context and self.chain_context.get("underlying") == underlying)
        chart_text = "✓ Fresh STRONG chart confirmation" if chart_ready else "• Fresh STRONG chart confirmation required"
        chain_text = "✓ OI/PCR analysis ready" if chain_ready else "• Selected-expiry OI/PCR analysis required"
        self.plan_status.setText(f"Trade plan checklist: {chart_text}  |  {chain_text}")
        score = self.chart_context.get("score") if self.chart_context else None
        score_text = f"Trade Plan Score: {score}/100" if score is not None else "Trade Plan Score: waiting for chart"
        chart_text = "✓ Score above 75" if chart_ready else "• Score above 75 required"
        chain_text = "✓ OI/PCR analysis ready" if chain_ready else "• Selected-expiry OI/PCR analysis required"
        self.plan_status.setText(f"{score_text} (minimum: >75)  |  {chart_text}  |  {chain_text}")
        self.create_plan_button.setEnabled(chart_ready and chain_ready)

    def prepare_live_workspace(self):
        """Open with current expiry/ATM data already loading when a live session exists."""
        if LiveSession.connected() and not self.contracts:
            self.load_contracts()

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
            f"Quantity: {plan['quantity']} ({plan['quantity'] // plan['contract']['lot_size']} lot(s))\n"
            + "\n".join(f"• {reason}" for reason in plan["reasons"]) + f"\n\n{plan['warning']}"
        )
        self.send_plan_button.setEnabled(True)

    def send_plan_to_journal(self):
        if not self.current_plan:
            return
        self.trade_plan_ready.emit(self.current_plan)

    def show_error(self, message):
        self.chain_loading = False
        self.auto_refresh_pending = False
        self.details.setText(f"Options data unavailable: {message}")
