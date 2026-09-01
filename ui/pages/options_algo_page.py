"""Options-only automatic paper controller with daily net kill switches."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QTime, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                               QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QTimeEdit, QVBoxLayout, QWidget)

from core.database_manager import Database
from core.market_session import IST, market_session
from core.settings_store import SettingsStore
from services.auto_paper_trader import run_auto_paper_cycle
from services.live_session import LiveSession
from services.analysis_scheduler import AnalysisScheduler
from services.options_algo_service import calculate_algo_day_state, calculate_validation_metrics


class _AlgoSignals(QObject):
    cycle_done = Signal(dict)
    cycle_failed = Signal(str)
    monitor_done = Signal(list)


class OptionsAlgoPage(QWidget):
    """One-session controller. Saved values survive upgrades; activation never does."""
    def __init__(self):
        super().__init__()
        self.store = SettingsStore(); self.signals = _AlgoSignals(); self.running = False
        self.session_active = False; self.last_candle_key = None; self.monitoring = False
        self.pending_symbol = "NIFTY"; self.pending_lots = 1
        self.signals.cycle_done.connect(self._cycle_finished)
        self.signals.cycle_failed.connect(self._cycle_failed)
        self.signals.monitor_done.connect(self._monitor_finished)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 24); layout.setSpacing(12); scroll.setWidget(body); outer.addWidget(scroll)
        title = QLabel("Options Algo Trading Control Center"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Cutie completed 5-minute candle, option liquidity, OI/PCR, trend aur safety evidence observe karke options PAPER trades automatically capture aur exit karti hai. "
            "Daily net target, maximum loss ya trade limit hit hote hi new-entry kill switch lagta hai. Open trade ki target/stop/time-exit monitoring hamesha active rehti hai."
        ); intro.setWordWrap(True); layout.addWidget(intro)

        controls_box = QGroupBox("Today's options algo boundaries — values save rahengi, activation session-only hai")
        controls = QGridLayout(controls_box)
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.target = QDoubleSpinBox(); self.target.setRange(0, 10_000_000); self.target.setPrefix("₹"); self.target.setDecimals(2)
        self.loss = QDoubleSpinBox(); self.loss.setRange(0, 10_000_000); self.loss.setPrefix("₹"); self.loss.setDecimals(2)
        self.max_trades = QSpinBox(); self.max_trades.setRange(1, 10); self.lots = QSpinBox(); self.lots.setRange(1, 100)
        self.charges = QDoubleSpinBox(); self.charges.setRange(0, 100_000); self.charges.setPrefix("₹"); self.charges.setDecimals(2)
        self.slippage = QDoubleSpinBox(); self.slippage.setRange(0, 100_000); self.slippage.setPrefix("₹"); self.slippage.setDecimals(2)
        self.entry_start = QTimeEdit(); self.entry_start.setDisplayFormat("HH:mm")
        self.last_entry = QTimeEdit(); self.last_entry.setDisplayFormat("HH:mm")
        settings = self.store.load()
        self.target.setValue(float(settings.get("options_algo_daily_target_net", 1000)))
        self.loss.setValue(float(settings.get("options_algo_daily_max_loss", 500)))
        self.max_trades.setValue(int(settings.get("options_algo_max_trades", 10)))
        self.lots.setValue(int(settings.get("options_algo_lots", 1)))
        self.charges.setValue(float(settings.get("options_algo_estimated_charges", 60)))
        self.slippage.setValue(float(settings.get("options_algo_estimated_slippage", 20)))
        self.entry_start.setTime(QTime.fromString(settings.get("options_algo_entry_start", "09:20"), "HH:mm"))
        self.last_entry.setTime(QTime.fromString(settings.get("options_algo_last_entry", "15:00"), "HH:mm"))
        controls.addWidget(QLabel("Index options"), 0, 0); controls.addWidget(self.symbol, 0, 1)
        controls.addWidget(QLabel("Daily target profit — net after estimated charges"), 1, 0); controls.addWidget(self.target, 1, 1)
        controls.addWidget(QLabel("Daily maximum loss — net after estimated charges"), 2, 0); controls.addWidget(self.loss, 2, 1)
        controls.addWidget(QLabel("Maximum captured trades/orders today (1–10)"), 3, 0); controls.addWidget(self.max_trades, 3, 1)
        controls.addWidget(QLabel("Lots per qualified trade"), 4, 0); controls.addWidget(self.lots, 4, 1)
        controls.addWidget(QLabel("Estimated round-trip charges per closed trade"), 5, 0); controls.addWidget(self.charges, 5, 1)
        controls.addWidget(QLabel("Estimated slippage per closed trade"), 6, 0); controls.addWidget(self.slippage, 6, 1)
        controls.addWidget(QLabel("New-entry window (completed candles only)"), 7, 0)
        window = QWidget(); window_layout = QGridLayout(window); window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.entry_start, 0, 0); window_layout.addWidget(QLabel("to"), 0, 1); window_layout.addWidget(self.last_entry, 0, 2)
        controls.addWidget(window, 7, 1)
        self.save_button = QPushButton("Save Today's Algo Boundaries"); self.save_button.clicked.connect(self.save_settings)
        controls.addWidget(self.save_button, 8, 0, 1, 2); layout.addWidget(controls_box)

        session_box = QGroupBox("Current application session")
        session = QGridLayout(session_box)
        self.enable = QCheckBox("Start options algo for this session (PAPER default)")
        self.enable.toggled.connect(self._toggle_session)
        self.mode = QLabel(); self.mode.setObjectName("cardValue")
        self.kill = QPushButton("Emergency Kill Switch — Stop New Entries"); self.kill.clicked.connect(self.emergency_stop)
        session.addWidget(self.enable, 0, 0, 1, 2); session.addWidget(QLabel("Execution mode"), 1, 0); session.addWidget(self.mode, 1, 1)
        session.addWidget(self.kill, 2, 0, 1, 2); layout.addWidget(session_box)

        cards = QGridLayout(); self.card_labels = {}
        for index, name in enumerate(("Algo state", "Gross realized P&L", "Estimated friction", "Net P&L", "Trades / limit", "Open positions")):
            box = QGroupBox(name); box_layout = QVBoxLayout(box); value = QLabel("-"); value.setObjectName("cardValue"); value.setWordWrap(True)
            box_layout.addWidget(value); cards.addWidget(box, index // 3, index % 3); self.card_labels[name] = value
        layout.addLayout(cards)
        quality_box = QGroupBox("Paper Validation & Deployment Readiness — real order authorization nahi")
        quality_layout = QVBoxLayout(quality_box); self.quality = QLabel(); self.quality.setWordWrap(True); quality_layout.addWidget(self.quality)
        layout.addWidget(quality_box)
        self.status = QLabel("Algo session stopped."); self.status.setWordWrap(True); layout.addWidget(self.status)
        disclosure = QLabel(
            "REAL mode: automatic broker entry tabhi available hogi jab broker fill reconciliation aur managed target/stop exit chain verified ho. "
            "Current controller incomplete real exits ko expose nahi karta; PAPER mode end-to-end automatic validation ke liye hai. Profit guaranteed nahi hai."
        ); disclosure.setWordWrap(True); layout.addWidget(disclosure); layout.addStretch()
        self.timer = QTimer(self); self.timer.setInterval(10_000); self.timer.timeout.connect(self.tick)
        QTimer.singleShot(AnalysisScheduler.stagger_ms("options-algo"), self.timer.start)
        self.refresh()

    def save_settings(self):
        settings = self.store.load(); settings.update({
            "options_algo_daily_target_net": self.target.value(), "options_algo_daily_max_loss": self.loss.value(),
            "options_algo_max_trades": self.max_trades.value(), "options_algo_estimated_charges": self.charges.value(),
            "options_algo_estimated_slippage": self.slippage.value(), "options_algo_lots": self.lots.value(),
            "options_algo_entry_start": self.entry_start.time().toString("HH:mm"),
            "options_algo_last_entry": self.last_entry.time().toString("HH:mm"),
        }); self.store.save(settings)
        self.status.setText(f"✓ Algo boundaries {datetime.now(IST).strftime('%d-%m-%Y %H:%M:%S IST')} par save ho gayi.")
        self.refresh()

    def apply_cutie_command(self, command: dict):
        """Apply only parser-produced, allow-listed commands; normal guards still decide execution."""
        intent = command.get("intent")
        if intent == "STOP_ALGO":
            self.emergency_stop(); return "Kill switch applied; new entries stopped."
        if intent == "ALGO_STATUS":
            self.refresh(); return self.status.text()
        if intent != "START_ALGO" or command.get("mode") != "PAPER":
            raise RuntimeError("Only guarded PAPER algo start is available from Cutie commands.")
        self.symbol.setCurrentIndex(max(0, self.symbol.findText(command["symbol"])))
        self.target.setValue(float(command["target"])); self.loss.setValue(float(command["max_loss"]))
        self.max_trades.setValue(int(command["max_trades"])); self.lots.setValue(int(command["lots"]))
        settings = self.store.load(); settings["execution_mode"] = "PAPER"; self.store.save(settings)
        self.save_settings()
        if not LiveSession.connected():
            self.status.setText("Command saved — broker data connect hone ke baad PAPER algo start karein.")
            return self.status.text()
        self.enable.setChecked(True)
        return self.status.text()

    def _toggle_session(self, checked):
        if checked:
            settings = self.store.load()
            if str(settings.get("execution_mode", "PAPER")).upper() == "REAL":
                self.enable.blockSignals(True); self.enable.setChecked(False); self.enable.blockSignals(False)
                QMessageBox.warning(self, "REAL algo locked", "Automatic REAL entry/exit reconciliation abhi certified nahi hai. Settings me PAPER mode select karke validation chalayein.")
                return
            if not LiveSession.connected():
                self.enable.blockSignals(True); self.enable.setChecked(False); self.enable.blockSignals(False)
                QMessageBox.warning(self, "Broker data", "Read-only broker live data connect kijiye, phir algo session start karein.")
                return
        self.session_active = checked
        if checked: self.save_settings(); self.status.setText("Cutie options algo active hai; next completed 5-minute candle observe ho rahi hai.")
        else: self.status.setText("Algo stopped. Existing open PAPER trade ki exit monitoring active rahegi.")
        self.refresh()

    def emergency_stop(self):
        self.session_active = False; self.enable.blockSignals(True); self.enable.setChecked(False); self.enable.blockSignals(False)
        self.status.setText("KILL SWITCH ACTIVE — new entries stopped; existing PAPER exits continue to be monitored."); self.refresh()

    def _progress(self):
        db = Database()
        try: return db.paper_trade_progress(datetime.now(IST).strftime("%d-%m-%Y"))
        finally: db.close()

    def refresh(self):
        settings = self.store.load(); mode = str(settings.get("execution_mode", "PAPER")).upper(); self.mode.setText(mode)
        state = calculate_algo_day_state(self._progress(), settings, session_active=self.session_active)
        values = {"Algo state": f"{state.state}\n{state.reason}", "Gross realized P&L": f"₹{state.gross_pnl:,.2f}",
                  "Estimated friction": f"Charges ₹{state.estimated_charges:,.2f}\nSlippage ₹{state.estimated_slippage:,.2f}", "Net P&L": f"₹{state.net_pnl:,.2f}",
                  "Trades / limit": f"{state.trades} / {state.trades + state.remaining_trades}", "Open positions": str(state.open_trades)}
        for name, value in values.items(): self.card_labels[name].setText(value)
        db = Database()
        try: metrics = calculate_validation_metrics(db.get_journal_rows(), settings)
        finally: db.close()
        factor = "∞" if metrics.profit_factor is None and metrics.closed_trades else ("-" if metrics.profit_factor is None else f"{metrics.profit_factor:.2f}")
        verdict = "REVIEW-READY" if metrics.ready_for_review else "PAPER EVIDENCE PENDING"
        self.quality.setText(
            f"{verdict} | Closed {metrics.closed_trades} | Wins {metrics.wins} | Win rate {metrics.win_rate:.1f}% | "
            f"Net expectancy ₹{metrics.expectancy:,.2f}/trade | Profit factor {factor} | Max drawdown ₹{metrics.max_drawdown:,.2f}\n"
            f"Gate: {metrics.reason} TPS real execution ko automatically unlock nahi karega."
        )
        if state.state in {"TARGET HIT", "LOSS LIMIT HIT", "TRADE LIMIT HIT"} and self.session_active:
            self.emergency_stop(); self.status.setText(f"AUTO KILL SWITCH — {state.reason} No new trade will be captured today.")

    def tick(self):
        if not LiveSession.connected() or self.running: return
        if not self.monitoring:
            self.monitoring = True
            if not AnalysisScheduler.submit_unique("options-algo-exit-monitor", self._monitor_worker):
                self.monitoring = False
        settings = self.store.load(); state = calculate_algo_day_state(self._progress(), settings, session_active=self.session_active)
        if not state.allow_new_entry or market_session(settings=settings)["state"] != "OPEN": return
        now = datetime.now(IST)
        start = QTime.fromString(settings.get("options_algo_entry_start", "09:20"), "HH:mm")
        end = QTime.fromString(settings.get("options_algo_last_entry", "15:00"), "HH:mm")
        current = QTime(now.hour, now.minute)
        if current < start or current > end:
            self.status.setText(f"New-entry window {start.toString('HH:mm')}–{end.toString('HH:mm')} ke bahar hai; open trade exits monitor ho rahe hain.")
            return
        candle_key = f"{now:%Y-%m-%d-%H}-{(now.minute // 5) * 5:02d}"
        if candle_key == self.last_candle_key: return
        self.last_candle_key = candle_key; self.running = True
        self.pending_symbol = self.symbol.currentText(); self.pending_lots = self.lots.value()
        if not AnalysisScheduler.submit_unique("options-algo-entry-cycle", self._cycle_worker):
            self.running = False

    def _monitor_worker(self):
        db = Database()
        try: rows = db.monitor_paper_trades(LiveSession.client, self.store.load())
        except Exception: rows = []
        finally: db.close()
        self.signals.monitor_done.emit(rows)

    def _monitor_finished(self, _rows):
        self.monitoring = False
        self.refresh()

    def _cycle_worker(self):
        try:
            result = run_auto_paper_cycle(
                LiveSession.client, self.pending_symbol, self.store.load(), requested_lots=self.pending_lots,
            )
            self.signals.cycle_done.emit(result)
        except Exception as error: self.signals.cycle_failed.emit(str(error))

    def _cycle_finished(self, result):
        self.running = False; outcome = result.get("attempt_outcome") or result.get("status") or "Checked"
        self.status.setText(f"Last completed-candle result: {outcome}. {result.get('status', '')}"); self.refresh()

    def _cycle_failed(self, message):
        self.running = False; self.status.setText(f"Algo data check unavailable: {message}. Cutie next cycle me retry karegi."); self.refresh()
