"""Research-only expiry option spike observation workspace."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, time

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.market_session import IST, parse_session_times
from engine.expiry_spike_engine import evaluate_spike, format_spike_event, predict_expiry_spike, select_nearby_expiry_contracts
from services.expiry_observation_store import ExpiryObservationStore
from services.live_session import LiveSession
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService


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
        self.history = defaultdict(lambda: deque(maxlen=24)); self.last_spot = {}; self.active_events = {}; self.running = False
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 24); layout.setSpacing(10); scroll.setWidget(body); outer.addWidget(scroll)
        title = QLabel("Expiry After 3 PM Observation"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Research + observation engine: expiry-day 3:00 PM ke baad nearby ATM/ITM premium acceleration, volume, OI, spot aur CAS context save karta hai. Yeh Buy/Sell signal nahi hai aur koi broker order place nahi karta.")
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout(); self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.underlying.currentTextChanged.connect(lambda: self.refresh_history())
        self.expiry_toggle = QCheckBox("Today is Expiry — 3 PM observation enable karein")
        self.expiry_toggle.setChecked(self.settings.value("expiry_observation/enabled", False, bool))
        self.expiry_toggle.toggled.connect(self._toggle); self.scan_button = QPushButton("Observe Expiry Window Now")
        self.scan_button.clicked.connect(lambda: self.scan(force=True)); controls.addWidget(QLabel("Index"), 0, 0); controls.addWidget(self.underlying, 0, 1)
        controls.addWidget(self.expiry_toggle, 1, 0, 1, 2); controls.addWidget(self.scan_button, 2, 0, 1, 2); layout.addLayout(controls)
        self.status = QLabel("Toggle OFF — no expiry monitoring."); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.cards = QLabel("Spot: - | Expiry: - | Tracked contracts: 0 | CAS: -"); self.cards.setObjectName("sectionCard"); layout.addWidget(self.cards)
        self.prediction = QLabel("Historical prediction: observation data collect ho raha hai.")
        self.prediction.setObjectName("sectionCard"); self.prediction.setWordWrap(True); layout.addWidget(self.prediction)
        layout.addWidget(QLabel("Spike Events — permanent historical log")); self.events_table = QTableWidget(0, 8)
        self.events_table.setHorizontalHeaderLabels(("Time", "Index", "Contract", "Strike", "Type", "Spike", "Duration", "Evidence")); self.events_table.setMinimumHeight(220); layout.addWidget(self.events_table)
        layout.addWidget(QLabel("Latest ATM / ITM observations")); self.obs_table = QTableWidget(0, 10)
        self.obs_table.setHorizontalHeaderLabels(("Time", "Contract", "Moneyness", "Premium", "% move", "Volume x", "OI", "OI change", "Spot", "Data")); self.obs_table.setMinimumHeight(260); layout.addWidget(self.obs_table)
        self.timer = QTimer(self); self.timer.setInterval(30000); self.timer.timeout.connect(self.scan); self.timer.start(); self.refresh_history()

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
        for item in rows:
            contract, quote = item["contract"], item["quote"]
            premium = float(quote.get("ltp", 0) or 0); volume = float(quote.get("tradeVolume", quote.get("volume", 0)) or 0)
            oi = float(quote.get("opnInterest", quote.get("openInterest", 0)) or 0); token = str(contract["token"])
            sample = {"observed_at": now, "premium": premium, "volume": volume, "open_interest": oi, "spot": spot}
            self.history[token].append(sample); result = evaluate_spike(list(self.history[token]), spot_breakout=abs(spot-prior_spot) >= max(5, spot*.00025))
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
            if result.get("event"):
                active = self.active_events.get(token)
                if active is None:
                    active = {"key": f"{now.date()}|{contract['symbol']}|{now.strftime('%H%M%S')}", "started_at": now, "peak": 0.0}
                    self.active_events[token] = active
                active["peak"] = max(float(active["peak"]), float(result["premium_change_pct"]))
                duration = max(0, int((now - active["started_at"]).total_seconds()))
                result["elapsed_seconds"] = duration
                event_text = format_spike_event(symbol, contract, result, now); key = active["key"]
                self.store.save_event({"event_key": key, "trade_date": now.date().isoformat(), "started_at": active["started_at"].isoformat(), "last_seen_at": now.isoformat(),
                    "underlying": symbol, "contract_symbol": contract["symbol"], "strike": contract["strike"], "option_type": contract["option_type"],
                    "moneyness": contract["moneyness"], "premium": premium, "peak_change_pct": active["peak"], "volume_ratio": result.get("volume_ratio"),
                    "oi_change_pct": result.get("oi_change_pct"), "spot": spot, "duration_seconds": result.get("elapsed_seconds", 0), "cas_context": context,
                    "underlying_move": spot-prior_spot,
                    "source_completeness": result.get("source_completeness", "PARTIAL"), "event_text": event_text})
            else:
                self.active_events.pop(token, None)
        self.cards.setText(f"Spot: {spot:,.2f} | Expiry: {payload['expiry'].strftime('%d-%m-%Y')} | Tracked contracts: {len(rows)} | CAS: {context}")
        self.status.setText(f"Last observation saved: {now.strftime('%d-%m-%Y %I:%M:%S %p')} | Research only")
        self.refresh_history()

    def refresh_history(self):
        events = self.store.events(); self.events_table.setRowCount(len(events))
        for r, row in enumerate(events):
            values = (row["started_at"], row["underlying"], row["contract_symbol"], f"{row['strike']:g}", row["option_type"],
                      f"{row['peak_change_pct']:+.1f}%", f"{row['duration_seconds']} sec", row["event_text"])
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
