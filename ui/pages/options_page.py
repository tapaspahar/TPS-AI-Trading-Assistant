from datetime import date
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from core.database_manager import Database
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
from engine.greeks_engine import calculate_greeks
from services.auto_paper_trader import run_auto_paper_cycle
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
    paper_trade_error = Signal(str)
    auto_paper_status = Signal(str)
    auto_paper_captured = Signal(object)

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
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Options Decision Workspace — verify every condition before placing a manual broker order."))

        selection = QGroupBox("1. Choose a contract")
        form = QFormLayout(selection)
        self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.underlying.currentTextChanged.connect(lambda _symbol: self.update_plan_readiness())
        self.expiry = QComboBox(); self.expiry.currentIndexChanged.connect(self.populate_strikes)
        self.option_type = QComboBox(); self.option_type.addItems(("CE", "PE")); self.option_type.currentIndexChanged.connect(self.populate_strikes)
        self.strike = QComboBox(); self.strike.currentIndexChanged.connect(self.schedule_auto_refresh)
        self.strike.currentIndexChanged.connect(self.update_lot_quantity)
        self.lots = QSpinBox(); self.lots.setRange(1, 100); self.lots.setValue(1); self.lots.valueChanged.connect(self.update_lot_quantity)
        self.event_check = QComboBox(); self.event_check.addItems(("Review news / event risk", "No known high-impact event", "High-impact event or expiry-day risk")); self.event_check.currentIndexChanged.connect(self.update_plan_readiness)
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
        self.paper_button = QPushButton("Capture Paper Trade (ATM, 1 Lot - no broker order)")
        self.paper_button.clicked.connect(self.capture_paper_trade)
        self.paper_button.setEnabled(False)
        layout.addWidget(self.paper_button)
        auto_box = QGroupBox("Auto Paper Trading - 20 trading-day forward validation only")
        auto_form = QFormLayout(auto_box)
        self.auto_paper_enabled = QCheckBox("Enable strict auto paper trades (ATM, 1 lot, no real order)")
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
        layout.addWidget(QLabel("TPS only analyses data. It does not place, modify, or cancel an Angel One order."))
        layout.addStretch()
        self.contracts_loaded.connect(self.show_contracts)
        self.load_error.connect(self.show_error)
        self.quote_loaded.connect(self.show_quote)
        self.quote_error.connect(self.show_error)
        self.chain_loaded.connect(self.show_chain_analysis)
        self.chain_error.connect(self.show_error)
        self.paper_trade_captured.connect(self.show_paper_trade_captured)
        self.paper_trade_closed.connect(self.show_paper_trade_closed)
        self.paper_trade_error.connect(self.show_paper_trade_error)
        self.auto_paper_status.connect(self.show_auto_paper_status)
        self.auto_paper_captured.connect(self.show_auto_paper_captured)
        self.paper_monitor_timer = QTimer(self)
        self.paper_monitor_timer.timeout.connect(self.monitor_paper_trades)
        self.auto_paper_timer = QTimer(self)
        self.auto_paper_timer.timeout.connect(self.check_auto_paper_cycle)

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

    def update_lot_quantity(self, *_args):
        contract = self.strike.currentData()
        if not contract:
            self.quantity_preview.setText("Quantity: load a contract")
            return
        lot_size = int(contract.get("lot_size", 0) or 0)
        self.quantity_preview.setText(f"{self.lots.value()} lot(s) × {lot_size} = {self.lots.value() * lot_size} quantity")

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
            greeks = calculate_greeks(self.spot_price, selected["strike"], selected_row["ltp"], selected.get("expiry"), selected["option_type"])
            if greeks:
                selected_text += f" | Greeks est. IV {greeks['iv']:.1f}% Δ {greeks['delta']:.3f} Θ/day {greeks['theta_per_day']:.2f}"
            else:
                selected_text += " | Greeks unavailable (no estimate created)"
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
            and self.chart_context.get("score", 0) >= 95
            and bool(self.chart_context.get("volume_confirmed"))
            and bool(self.chart_context.get("trade_ready"))
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
        open_trade = self.db.has_open_trade(underlying)
        expiry_day = self.expiry.currentData() == date.today()
        event_ready = self.event_check.currentText() == "No known high-impact event" and not expiry_day
        event_text = "⚠ Expiry-day caution: TPS blocks new plans; review manually" if expiry_day else (
            "✓ News/event check recorded" if event_ready else "• Confirm no high-impact news/event before planning"
        )
        open_text = "[!] Close/review the active open trade before a new plan" if open_trade else "[OK] No active open trade for this underlying"
        self.plan_status.setText(
            f"{score_text} (minimum: 95)  |  "
            f"{'✓ Score 95+ with high-volume confirmation' if chart_ready else '• Score 95+ and Volume > Volume EMA 20 required'}  |  "
            f"{chain_text}  |  {event_text}  |  {open_text}"
        )
        ready = chart_ready and chain_ready and event_ready and not open_trade
        self.create_plan_button.setEnabled(ready)
        self.paper_button.setEnabled(ready)

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
            contracts = [contract for contract in self.contracts if contract["expiry"] == expiry]
            plan = create_review_plan(
                self.underlying.currentText(), self.spot_price, contracts, self.chain_context["quote_rows"],
                self.chart_context, self.chain_context, SettingsStore().load(), requested_lots=1,
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
            f"PAPER TRADE CAPTURED - no Angel One order was sent.\n{plan['contract']['symbol']} | ATM / 1 lot | "
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
            closed = database.monitor_paper_trades(LiveSession.client)
            if closed:
                self.paper_trade_closed.emit(closed)
        except (RuntimeError, ValueError) as error:
            self.paper_trade_error.emit(str(error))
        finally:
            database.close()
            self.paper_monitoring = False

    def show_paper_trade_closed(self, closed):
        summary = "; ".join(f"{item['symbol']} {item['outcome']} at {item['ltp']:.2f}" for item in closed)
        self.details.setText(f"PAPER TRADE AUTO-BOOKED: {summary}. It has been saved in Trade Journal; review the result before using any real-money plan.")
        self.update_plan_readiness()

    def show_paper_trade_error(self, message):
        self.details.setText(f"Paper-trade monitor paused: {message}. No broker order was sent; retry after Angel One data is available.")

    def set_auto_paper_enabled(self, enabled: bool):
        if enabled:
            if self.event_check.currentText() != "No known high-impact event":
                self.auto_paper_enabled.blockSignals(True); self.auto_paper_enabled.setChecked(False); self.auto_paper_enabled.blockSignals(False)
                QMessageBox.warning(self, "Auto paper trading", "First select 'No known high-impact event' after checking news/events. TPS will not automate around an unreviewed event.")
                return
            if not LiveSession.connected():
                self.auto_paper_enabled.blockSignals(True); self.auto_paper_enabled.setChecked(False); self.auto_paper_enabled.blockSignals(False)
                QMessageBox.warning(self, "Auto paper trading", "Connect Angel One read-only data first.")
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
        now = __import__("datetime").datetime.now()
        market_open = now.weekday() < 5 and ((now.hour == 9 and now.minute >= 15) or 10 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30))
        if not market_open:
            self.auto_paper_status.emit("Auto paper mode is waiting for NSE market hours (09:15-15:30).")
            return
        bucket = now.strftime("%Y-%m-%d %H:") + str(now.minute // 5)
        if bucket == self.last_auto_paper_bucket:
            return
        self.last_auto_paper_bucket = bucket
        self.auto_paper_running = True
        self.auto_paper_status.emit("Checking completed 5-minute future candle, volume, OI/PCR and 95-score conditions…")
        Thread(target=self._run_auto_paper_cycle, args=(self.underlying.currentText(),), daemon=True).start()

    def _run_auto_paper_cycle(self, symbol):
        try:
            result = run_auto_paper_cycle(LiveSession.client, symbol, SettingsStore().load())
            if result.get("plan"):
                self.auto_paper_captured.emit(result)
            else:
                self.auto_paper_status.emit(result["status"])
        except (RuntimeError, ValueError) as error:
            self.auto_paper_status.emit(f"Auto paper cycle skipped: {error}")
        finally:
            self.auto_paper_running = False

    def show_auto_paper_status(self, message):
        progress = self.db.paper_trade_progress()
        self.auto_paper_progress.setText(f"{message}\nForward-test progress: {progress['days']}/20 trading days | {progress['trades']} paper trades | {progress['target_hits']} targets | {progress['stoploss_hits']} stop losses.")

    def show_auto_paper_captured(self, result):
        plan = result["plan"]
        progress = self.db.paper_trade_progress()
        self.auto_paper_progress.setText(
            f"PAPER TRADE #{result['trade_id']} captured: {plan['contract']['symbol']} | 1 lot / {plan['quantity']} qty | "
            f"Entry {plan['entry']:.2f}, Stop {plan['stoploss']:.2f}, Target {plan['target']:.2f}. Live quote monitoring is active.\n"
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
