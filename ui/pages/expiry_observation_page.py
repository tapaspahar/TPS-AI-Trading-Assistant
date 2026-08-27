"""Research-only expiry option spike observation workspace."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, time

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                               QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.database_manager import Database
from core.market_session import IST, parse_session_times
from core.settings_store import SettingsStore
from engine.expiry_spike_engine import evaluate_spike, format_spike_event, predict_expiry_spike, select_nearby_expiry_contracts
from services.expiry_observation_store import ExpiryObservationStore
from services.live_session import LiveSession
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService
from services.paired_execution_service import PairedExecutionService


def expiry_monitor_window(now, enabled, expiry_date, market_close):
    if not enabled:
        return "OFF"
    if expiry_date != now.date():
        return "NOT EXPIRY"
    if now.time() < time(15, 0):
        return "ARMED UNTIL 3:00 PM"
    if now.time() >= market_close:
        return "MARKET CLOSED"
    return "MONITORING"


def cas_context(now):
    if now.time() < time(15, 15):
        return "PRE-CAS / CONTINUOUS INDEX SESSION"
    if now.time() < time(15, 30):
        return "CAS OVERLAP: INDEX OPTIONS CONTINUOUS; CASH CAS CONTEXT ONLY"
    return "POST-CLOSE"


class _Signals(QObject):
    done = Signal(dict)
    failed = Signal(str)


class _ScanTask(QRunnable):
    def __init__(self, underlying):
        super().__init__(); self.underlying = underlying; self.signals = _Signals()

    def run(self):
        try:
            client = LiveSession.client
            if client is None:
                raise RuntimeError("Broker live data connect kijiye; monitor read-only quote data use karta hai.")
            service = OptionContractService()
            spot_item = UNDERLYING_QUOTES[self.underlying]
            spot = float(client.get_option_quote(spot_item["exchange"], spot_item["token"]).get("ltp", 0) or 0)
            contracts = service.get_contracts(self.underlying)
            selected = select_nearby_expiry_contracts(contracts, spot)
            if not selected or selected[0]["expiry"] != datetime.now(IST).date():
                expiry = min((row["expiry"] for row in contracts), default=None)
                self.signals.done.emit({"underlying": self.underlying, "spot": spot, "expiry": expiry, "rows": []}); return
            by_exchange = {}
            for row in selected:
                by_exchange.setdefault(row["exchange"], []).append(row["token"])
            quotes = []
            for exchange, tokens in by_exchange.items():
                quotes.extend(client.get_option_chain_quotes(exchange, tokens))
            quote_by_token = {str(row.get("symbolToken") or row.get("token")): row for row in quotes}
            rows = []
            for contract in selected:
                quote = quote_by_token.get(str(contract["token"]), {})
                rows.append({"contract": contract, "quote": quote})
            self.signals.done.emit({"underlying": self.underlying, "spot": spot, "expiry": selected[0]["expiry"], "rows": rows})
        except Exception as error:
            self.signals.failed.emit(str(error))


class ExpiryObservationPage(QWidget):
    def __init__(self):
        super().__init__()
        self.store = ExpiryObservationStore(); self.settings = QSettings("TPS", "TPS AI Trading Assistant")
        self.db = Database(); self.settings_store = SettingsStore()
        self.pair_execution = PairedExecutionService(self.db, self.settings_store, LiveSession)
        self.history = defaultdict(lambda: deque(maxlen=24)); self.last_spot = {}; self.active_events = {}
        self.latest_pairs = {}; self.running = False
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 24); layout.setSpacing(10); scroll.setWidget(body); outer.addWidget(scroll)
        title = QLabel("Expiry After 3 PM Observation"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Expiry research engine nearby ATM/ITM premium acceleration, volume, OI, spot aur CAS context save karta hai. Optional same-strike CE+PE execution long-straddle hai: profit guaranteed nahi; IV crush, theta, spread, slippage aur dono premiums girne ka risk hai. PAPER default hai.")
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout(); self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.underlying.currentTextChanged.connect(lambda: self.refresh_history())
        self.expiry_toggle = QCheckBox("Today is Expiry — 3 PM observation enable karein")
        self.expiry_toggle.setChecked(self.settings.value("expiry_observation/enabled", False, bool))
        self.expiry_toggle.toggled.connect(self._toggle); self.scan_button = QPushButton("Observe Expiry Window Now")
        self.scan_button.clicked.connect(lambda: self.scan(force=True)); controls.addWidget(QLabel("Index"), 0, 0); controls.addWidget(self.underlying, 0, 1)
        controls.addWidget(self.expiry_toggle, 1, 0, 1, 2); controls.addWidget(self.scan_button, 2, 0, 1, 2); layout.addLayout(controls)
        execution_box = QGroupBox("Same-strike CE + PE Pair — guarded paper/real execution")
        execution = QGridLayout(execution_box)
        self.pair_lots = QSpinBox(); self.pair_lots.setRange(1, 20)
        self.pair_lots.setValue(self.settings.value("expiry_pair/lots", 1, int))
        self.pair_target = QDoubleSpinBox(); self.pair_target.setRange(1, 1000000); self.pair_target.setPrefix("₹")
        self.pair_target.setValue(self.settings.value("expiry_pair/target", 1000.0, float))
        self.pair_stop = QDoubleSpinBox(); self.pair_stop.setRange(1, 1000000); self.pair_stop.setPrefix("₹")
        self.pair_stop.setValue(self.settings.value("expiry_pair/stop", 500.0, float))
        self.pair_time = QLineEdit(self.settings.value("expiry_pair/time_exit", "15:25")); self.pair_time.setPlaceholderText("HH:MM")
        self.auto_pair = QCheckBox("Spike confirmed hone par auto pair capture/submit (sirf current session)")
        self.auto_pair.setChecked(False)
        self.paper_pair = QPushButton("Capture PAPER CE+PE Pair"); self.paper_pair.clicked.connect(lambda: self._place_pair(False))
        self.arm_pair = QPushButton("Arm REAL Pair Session"); self.arm_pair.clicked.connect(self._arm_real_pair)
        self.real_pair = QPushButton("Place REAL CE+PE Pair"); self.real_pair.clicked.connect(lambda: self._place_pair(True))
        self.stop_pair = QPushButton("Emergency Stop / Disarm"); self.stop_pair.clicked.connect(self._emergency_stop)
        execution.addWidget(QLabel("Lots"), 0, 0); execution.addWidget(self.pair_lots, 0, 1)
        execution.addWidget(QLabel("Combined target P&L"), 0, 2); execution.addWidget(self.pair_target, 0, 3)
        execution.addWidget(QLabel("Combined maximum loss"), 1, 0); execution.addWidget(self.pair_stop, 1, 1)
        execution.addWidget(QLabel("Time exit (HH:MM)"), 1, 2); execution.addWidget(self.pair_time, 1, 3)
        execution.addWidget(self.auto_pair, 2, 0, 1, 4)
        execution.addWidget(self.paper_pair, 3, 0); execution.addWidget(self.arm_pair, 3, 1)
        execution.addWidget(self.real_pair, 3, 2); execution.addWidget(self.stop_pair, 3, 3)
        self.pair_status = QLabel("No open expiry pair. REAL authority har app restart par locked rahegi.")
        self.pair_status.setWordWrap(True); execution.addWidget(self.pair_status, 4, 0, 1, 4)
        layout.addWidget(execution_box)
        for field in (self.pair_lots, self.pair_target, self.pair_stop, self.pair_time):
            if hasattr(field, "valueChanged"): field.valueChanged.connect(self._save_pair_preferences)
            else: field.editingFinished.connect(self._save_pair_preferences)
        self.status = QLabel("Toggle OFF — no expiry monitoring."); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.cards = QLabel("Spot: - | Expiry: - | Tracked contracts: 0 | CAS: -"); self.cards.setObjectName("sectionCard"); layout.addWidget(self.cards)
        self.prediction = QLabel("Historical prediction: observation data collect ho raha hai.")
        self.prediction.setObjectName("sectionCard"); self.prediction.setWordWrap(True); layout.addWidget(self.prediction)
        layout.addWidget(QLabel("Spike Events — same-strike CE/PE paired movement log")); self.events_table = QTableWidget(0, 12)
        self.events_table.setHorizontalHeaderLabels(("Time", "Index", "Contract", "Strike", "Type", "Start", "Spike", "Latest",
                                                     "Opposite", "Opp. start", "Opp. event", "Opp. latest")); self.events_table.setMinimumHeight(220); layout.addWidget(self.events_table)
        layout.addWidget(QLabel("Latest ATM / ITM observations")); self.obs_table = QTableWidget(0, 10)
        self.obs_table.setHorizontalHeaderLabels(("Time", "Contract", "Moneyness", "Premium", "% move", "Volume x", "OI", "OI change", "Spot", "Data")); self.obs_table.setMinimumHeight(260); layout.addWidget(self.obs_table)
        self.timer = QTimer(self); self.timer.setInterval(30000); self.timer.timeout.connect(self.scan); self.timer.start(); self.refresh_history()

    def _save_pair_preferences(self, *_):
        self.settings.setValue("expiry_pair/lots", self.pair_lots.value())
        self.settings.setValue("expiry_pair/target", self.pair_target.value())
        self.settings.setValue("expiry_pair/stop", self.pair_stop.value())
        self.settings.setValue("expiry_pair/time_exit", self.pair_time.text().strip())

    def _arm_real_pair(self):
        execution_phrase, ok = QInputDialog.getText(self, "Arm real execution", "Type ENABLE REAL TRADING:")
        if not ok: return
        pair_phrase, ok = QInputDialog.getText(self, "Arm expiry pair", "Type ARM EXPIRY PAIR:")
        if not ok: return
        try:
            self.pair_execution.arm_real(execution_phrase, pair_phrase)
            self.pair_status.setText("REAL pair session ARMED. App close/restart par authority expire ho jayegi.")
        except Exception as error:
            QMessageBox.warning(self, "Real pair locked", str(error))

    def _emergency_stop(self):
        self.auto_pair.setChecked(False); self.pair_execution.emergency_stop()
        self.pair_status.setText("Emergency stop active: new REAL pair submission locked. Existing broker positions manually verify karein.")

    def _candidate_pair(self, strike=None):
        candidates = self.latest_pairs.get(self.underlying.currentText(), {})
        if not candidates: raise RuntimeError("Fresh same-strike CE/PE quotes abhi available nahi hain.")
        if strike is None:
            strike = min(candidates, key=lambda value: abs(value - self.last_spot.get(self.underlying.currentText(), value)))
        pair = candidates.get(float(strike))
        if not pair or "CE" not in pair or "PE" not in pair:
            raise RuntimeError("Selected strike ke fresh CE aur PE dono quotes nahi mile.")
        return float(strike), pair

    def _place_pair(self, real, strike=None, automatic=False):
        try:
            strike, pair = self._candidate_pair(strike)
            if real and not automatic:
                answer = QMessageBox.question(
                    self, "Confirm real long straddle",
                    f"REAL BUY {self.pair_lots.value()} lot(s) CE + PE at strike {strike:g}?\n"
                    f"Combined target ₹{self.pair_target.value():,.2f}; max loss ₹{self.pair_stop.value():,.2f}.\n"
                    "Profit guaranteed nahi hai. Broker fills aur positions verify karna hoga.",
                )
                if answer != QMessageBox.Yes: return
            result = self.pair_execution.open_pair(
                underlying=self.underlying.currentText(), expiry=pair["expiry"], strike=strike,
                ce=pair["CE"], pe=pair["PE"], lots=self.pair_lots.value(),
                target_pnl=self.pair_target.value(), stop_pnl=self.pair_stop.value(),
                time_exit=self.pair_time.text().strip(), real=real,
            )
            self.pair_status.setText(f"{result['status']}: {strike:g} CE+PE pair recorded. Combined exits are being monitored.")
        except Exception as error:
            self.pair_status.setText(f"Pair blocked: {error}")
            if not automatic: QMessageBox.warning(self, "Pair not placed", str(error))

    def _monitor_open_pair(self):
        pair = self.db.get_open_execution_pair(self.underlying.currentText())
        if not pair: return
        quotes = self.latest_pairs.get(str(pair["underlying"]), {}).get(float(pair["strike"]), {})
        if "CE" not in quotes or "PE" not in quotes:
            self.pair_status.setText("Open pair exists; fresh CE/PE quotes ka wait ho raha hai. Broker position verify rakhein.")
            return
        try:
            result = self.pair_execution.update_from_quotes(pair, quotes["CE"]["premium"], quotes["PE"]["premium"])
            suffix = f" | Exit: {result['exit_reason']}" if result.get("exit_reason") else ""
            self.pair_status.setText(f"{pair['mode']} pair {pair['strike']:g}: combined P&L ₹{result['pnl']:,.2f}{suffix}")
        except Exception as error:
            self.auto_pair.setChecked(False)
            self.pair_status.setText(f"PAIR ATTENTION REQUIRED: {error}")

    def _toggle(self, checked):
        self.settings.setValue("expiry_observation/enabled", checked)
        self.status.setText("Expiry monitor armed." if checked else "Toggle OFF — no expiry monitoring.")
        if checked: self.scan()

    def scan(self, force=False):
        if self.running: return
        now = datetime.now(IST); _, _, close = parse_session_times(); symbol = self.underlying.currentText()
        try:
            nearest = min(row["expiry"] for row in OptionContractService().get_contracts(symbol))
        except Exception as error:
            self.status.setText(str(error)); return
        state = expiry_monitor_window(now, self.expiry_toggle.isChecked(), nearest, close)
        self.status.setText(f"Status: {state} | Nearest expiry: {nearest.strftime('%d-%m-%Y')} | Poll: 30 seconds")
        # A manual refresh must never bypass the expiry-day/3 PM/market-close gate.
        if state != "MONITORING": return
        self.running = True; self.scan_button.setEnabled(False); task = _ScanTask(symbol)
        task.signals.done.connect(self._consume); task.signals.failed.connect(self._failed); QThreadPool.globalInstance().start(task)

    def _failed(self, message):
        self.running = False; self.scan_button.setEnabled(True); self.status.setText(f"Data unavailable: {message}")

    def _consume(self, payload):
        self.running = False; self.scan_button.setEnabled(True); now = datetime.now(IST)
        # Keep the completed worker result attached to the index it actually
        # fetched even if the user changed the selector while it was running.
        symbol = str(payload.get("underlying") or self.underlying.currentText())
        spot = float(payload.get("spot") or 0); prior_spot = self.last_spot.get(symbol, spot); self.last_spot[symbol] = spot
        context = cas_context(now); rows = payload.get("rows") or []
        if not rows:
            self.status.setText("Today selected index ki expiry nahi hai; observation save nahi hua."); return
        current = {}
        results = {}
        for item in rows:
            contract, quote = item["contract"], item["quote"]
            premium = float(quote.get("ltp", 0) or 0); volume = float(quote.get("tradeVolume", quote.get("volume", 0)) or 0)
            oi = float(quote.get("opnInterest", quote.get("openInterest", 0)) or 0); token = str(contract["token"])
            sample = {"observed_at": now, "premium": premium, "volume": volume, "open_interest": oi, "spot": spot}
            self.history[token].append(sample); result = evaluate_spike(list(self.history[token]), spot_breakout=abs(spot-prior_spot) >= max(5, spot*.00025))
            pair_key = (float(contract["strike"]), str(contract["option_type"]).upper())
            current[pair_key] = {"contract": contract, "premium": premium, "token": token}
            results[token] = result
            row = {"observed_at": now.isoformat(), "trade_date": now.date().isoformat(), "underlying": symbol,
                   "expiry": contract["expiry"].isoformat(), "contract_symbol": contract["symbol"], "strike": contract["strike"],
                   "option_type": contract["option_type"], "moneyness": contract["moneyness"], "atm_distance": contract["atm_distance"],
                   "spot": spot, "premium": premium, "premium_change_pct": result.get("premium_change_pct"), "volume": volume,
                   "volume_ratio": result.get("volume_ratio"), "open_interest": oi, "oi_change": result.get("oi_change"),
                   "oi_change_pct": result.get("oi_change_pct"), "underlying_move": spot-prior_spot,
                   "iv": quote.get("impliedVolatility") or quote.get("iv"), "delta": quote.get("delta"), "gamma": quote.get("gamma"),
                   "theta": quote.get("theta"), "vega": quote.get("vega"), "sustain_seconds": result.get("elapsed_seconds", 0) if result.get("event") else 0,
                   "cas_context": context, "source_completeness": result.get("source_completeness", "PARTIAL")}
            self.store.save_observation(row)
        paired = defaultdict(dict)
        for (strike, option_type), value in current.items():
            if value["premium"] > 0:
                paired[strike][option_type] = {"contract": value["contract"], "premium": value["premium"]}
                paired[strike]["expiry"] = value["contract"]["expiry"]
        self.latest_pairs[symbol] = dict(paired)
        pair_auto_attempted = False
        # Save or update paired spike events only after all CE and PE quotes from
        # this poll are available, so both sides share the exact same timestamp.
        for item in rows:
            contract = item["contract"]; token = str(contract["token"]); result = results[token]
            premium = current[(float(contract["strike"]), str(contract["option_type"]).upper())]["premium"]
            opposite_type = "PE" if str(contract["option_type"]).upper() == "CE" else "CE"
            opposite = current.get((float(contract["strike"]), opposite_type))
            active = self.active_events.get(token)
            if result.get("event"):
                if active is None:
                    opposite_history = list(self.history[opposite["token"]]) if opposite else []
                    opposite_start = float(opposite_history[0].get("premium", 0)) if opposite_history else None
                    active = {"key": f"{now.date()}|{contract['symbol']}|{now.strftime('%H%M%S')}", "started_at": now,
                              "peak": 0.0, "spike_start": result.get("baseline_premium"), "spike_event": premium,
                              "opposite_symbol": opposite["contract"]["symbol"] if opposite else "",
                              "opposite_type": opposite_type, "opposite_start": opposite_start,
                              "opposite_event": opposite["premium"] if opposite else None}
                    self.active_events[token] = active
                active["peak"] = max(float(active["peak"]), float(result["premium_change_pct"]))
                if self.auto_pair.isChecked() and not pair_auto_attempted and symbol == self.underlying.currentText():
                    pair_auto_attempted = True
                    real = str(self.settings_store.load().get("execution_mode", "PAPER")).upper() == "REAL"
                    self._place_pair(real, float(contract["strike"]), automatic=True)
            if active is not None:
                duration = max(0, int((now - active["started_at"]).total_seconds()))
                result["elapsed_seconds"] = duration
                event_text = format_spike_event(symbol, contract, result, now); key = active["key"]
                opposite_latest = opposite["premium"] if opposite else None
                opposite_start = active.get("opposite_start")
                opposite_change = ((opposite_latest - opposite_start) / opposite_start * 100
                                   if opposite_latest is not None and opposite_start else None)
                self.store.save_event({"event_key": key, "trade_date": now.date().isoformat(), "started_at": active["started_at"].isoformat(), "last_seen_at": now.isoformat(),
                    "underlying": symbol, "contract_symbol": contract["symbol"], "strike": contract["strike"], "option_type": contract["option_type"],
                    "moneyness": contract["moneyness"], "premium": premium, "peak_change_pct": active["peak"], "volume_ratio": result.get("volume_ratio"),
                    "oi_change_pct": result.get("oi_change_pct"), "spot": spot, "duration_seconds": result.get("elapsed_seconds", 0), "cas_context": context,
                    "underlying_move": spot-prior_spot,
                    "source_completeness": result.get("source_completeness", "PARTIAL"), "event_text": event_text,
                    "spike_start_premium": active.get("spike_start"), "spike_event_premium": active.get("spike_event"),
                    "spike_latest_premium": premium, "opposite_contract_symbol": active.get("opposite_symbol"),
                    "opposite_option_type": active.get("opposite_type"), "opposite_start_premium": opposite_start,
                    "opposite_event_premium": active.get("opposite_event"), "opposite_latest_premium": opposite_latest,
                    "opposite_change_pct": opposite_change, "paired_last_updated_at": now.isoformat()})
            if active is not None and not result.get("event") and (now - active["started_at"]).total_seconds() >= 600:
                self.active_events.pop(token, None)
        self.cards.setText(f"Spot: {spot:,.2f} | Expiry: {payload['expiry'].strftime('%d-%m-%Y')} | Tracked contracts: {len(rows)} | CAS: {context}")
        self.status.setText(f"Last observation saved: {now.strftime('%d-%m-%Y %I:%M:%S %p')} | Observation + guarded pair monitoring")
        self._monitor_open_pair()
        self.refresh_history()

    def refresh_history(self):
        events = self.store.events(); self.events_table.setRowCount(len(events))
        for r, row in enumerate(events):
            money = lambda value: "-" if value is None else f"₹{float(value):,.2f}"
            values = (row["started_at"], row["underlying"], row["contract_symbol"], f"{row['strike']:g}", row["option_type"],
                      money(row.get("spike_start_premium")), money(row.get("spike_event_premium")), money(row.get("spike_latest_premium")),
                      f"{row.get('opposite_option_type') or '-'} {row.get('opposite_contract_symbol') or ''}".strip(),
                      money(row.get("opposite_start_premium")), money(row.get("opposite_event_premium")), money(row.get("opposite_latest_premium")))
            for c, value in enumerate(values): self.events_table.setItem(r, c, QTableWidgetItem(str(value)))
        today, symbol = datetime.now(IST).date().isoformat(), self.underlying.currentText(); observations = self.store.observations(today, symbol, 100)
        forecast = predict_expiry_spike(
            observations,
            self.store.historical_observations(symbol),
            self.store.historical_events(symbol),
        )
        self.prediction.setText("Expiry pattern prediction: " + forecast["text"])
        self.obs_table.setRowCount(len(observations))
        for r, row in enumerate(observations):
            values = (row["observed_at"], row["contract_symbol"], row["moneyness"], f"₹{row['premium']:,.2f}",
                      "-" if row["premium_change_pct"] is None else f"{row['premium_change_pct']:+.1f}%",
                      "-" if row["volume_ratio"] is None else f"{row['volume_ratio']:.1f}x", f"{row['open_interest']:,.0f}",
                      "-" if row["oi_change_pct"] is None else f"{row['oi_change_pct']:+.1f}%", f"{row['spot']:,.2f}", row["source_completeness"])
            for c, value in enumerate(values): self.obs_table.setItem(r, c, QTableWidgetItem(str(value)))
