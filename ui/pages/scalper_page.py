"""Fast completed-candle scalp watcher with transparent global context."""
from __future__ import annotations

from datetime import datetime, timedelta
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.scalper_service import ScalperService
from core.market_session import market_session


class ScalperPage(QWidget):
    analysis_ready = Signal(dict)
    analysis_failed = Signal(str)
    scalp_alert = Signal(dict)

    def __init__(self):
        super().__init__()
        self._running = False
        self._last_alert = None
        self._global_context = None
        self._global_at = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("TPS Near-Expiry Options Scalper"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Nearest-expiry ATM/near-ATM CE/PE strike ke liye fast scalp watch. Index future candles sirf direction aur traded-volume evidence deti hain; "
            "actual Entry, SL aur Targets selected option premium ki completed 1-minute candles se bante hain."
        ); note.setWordWrap(True); layout.addWidget(note)
        controls = QHBoxLayout()
        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX")); controls.addWidget(self.index, 2)
        self.strike_mode = QComboBox(); self.strike_mode.addItems(("ATM", "1-step ITM", "1-step OTM")); controls.addWidget(self.strike_mode, 1)
        self.threshold = QSpinBox(); self.threshold.setRange(60, 95); self.threshold.setValue(72); self.threshold.setSuffix(" / 100"); controls.addWidget(self.threshold, 1)
        self.auto = QCheckBox("Auto monitor every 20 seconds"); self.auto.setChecked(True); controls.addWidget(self.auto, 2)
        layout.addLayout(controls)
        self.run = QPushButton("Analyze Latest Completed Scalp Candle"); self.run.clicked.connect(lambda: self.analyze(force=True)); layout.addWidget(self.run)
        self.status = QLabel("Read-only broker connect karke monitoring start hogi."); self.status.setWordWrap(True); layout.addWidget(self.status)
        grid = QGridLayout(); self.cards = {}
        for column, name in enumerate(("Option Scalp Action", "Selected Near-Expiry Strike", "Option Premium Entry", "Premium SL / Targets")):
            box = QGroupBox(name); box_layout = QVBoxLayout(box); value = QLabel("-")
            value.setObjectName("metricValue"); value.setWordWrap(True); box_layout.addWidget(value)
            grid.addWidget(box, 0, column); self.cards[name] = value
        layout.addLayout(grid)
        global_box = QGroupBox("Global Market Context — confirmation only")
        global_layout = QVBoxLayout(global_box); self.global_text = QLabel("Official GIFT Nifty and reference global breadth not loaded yet.")
        self.global_text.setWordWrap(True); global_layout.addWidget(self.global_text); layout.addWidget(global_box)
        evidence_box = QGroupBox("Why TPS Published or Waited")
        evidence_layout = QVBoxLayout(evidence_box); self.evidence = QLabel("Run analysis to view every passed and failed condition.")
        self.evidence.setWordWrap(True); evidence_layout.addWidget(self.evidence); layout.addWidget(evidence_box)
        safety = QLabel("Safety: SCALP WATCH is not execution advice. Verify option premium, spread, liquidity, expiry, event risk and quantity before any manual/paper action.")
        safety.setWordWrap(True); layout.addWidget(safety); layout.addStretch()
        self.analysis_ready.connect(self.show_result); self.analysis_failed.connect(self.show_error)
        self.timer = QTimer(self); self.timer.setInterval(20_000); self.timer.timeout.connect(self.analyze); self.timer.start()

    def start_monitoring(self):
        if self.auto.isChecked():
            QTimer.singleShot(1_000, self.analyze)

    def analyze(self, force=False):
        if self._running or not LiveSession.connected() or (not force and not self.auto.isChecked()):
            return
        session = market_session()
        if session["state"] != "OPEN":
            self.status.setText(f"Live scalp monitor paused — {session['label']}. Stale candle par suggestion publish nahi hogi.")
            return
        self._running = True; self.run.setEnabled(False)
        self.status.setText("Future direction aur selected near-expiry option premium ki completed candles analyze ho rahi hain...")
        refresh_global = self._global_at is None or datetime.now() - self._global_at > timedelta(minutes=5)
        Thread(target=self._worker, args=(self.index.currentText(), self.threshold.value(), self.strike_mode.currentText(), refresh_global), daemon=True).start()

    def _worker(self, symbol, threshold, strike_mode, refresh_global):
        try:
            service = ScalperService(LiveSession.client)
            context = None if refresh_global else self._global_context
            self.analysis_ready.emit(service.analyze(symbol, threshold, context, strike_mode))
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            self.analysis_failed.emit(str(error))
        except Exception as error:
            self.analysis_failed.emit(f"Temporary data error: {error}")

    def show_result(self, result):
        self._global_context = result.get("global_context") or {}; self._global_at = datetime.now()
        self.cards["Option Scalp Action"].setText(f"{result['action']}\nScore {result['score']}/100")
        option = result.get("option_liquidity") or {}
        if result.get("option_contract"):
            self.cards["Selected Near-Expiry Strike"].setText(
                f"{option.get('symbol')}\n{option.get('strike_mode')} | Expiry {option.get('expiry')}"
            )
        if result.get("entry_reference") is not None:
            self.cards["Option Premium Entry"].setText(
                f"₹{result['entry_reference']:,.2f}\nLTP ₹{option.get('ltp', 0):,.2f} | Ask ₹{option.get('ask', 0):,.2f}"
            )
            self.cards["Premium SL / Targets"].setText(
                f"SL {result['stop']:,.2f}\nT1 {result['target1']:,.2f} | T2 {result['target2']:,.2f}"
            )
        elif result.get("option_contract"):
            self.cards["Option Premium Entry"].setText(
                f"LTP {option.get('ltp', 0):,.2f}\nPremium candles loading"
            )
            self.cards["Premium SL / Targets"].setText("WAIT\nNo premium plan yet")
        else:
            self.cards["Selected Near-Expiry Strike"].setText("No CE/PE strike selected")
            self.cards["Option Premium Entry"].setText("Waiting for direction")
            self.cards["Premium SL / Targets"].setText("No premium plan")
        context = self._global_context; gift = context.get("gift_nifty") or {}
        gift_text = (f"{gift.get('price', 0):,.2f} ({gift.get('change_percent', 0):+.2f}%)" if gift.get("available") else gift.get("status", "Unavailable"))
        references = " | ".join(
            f"{row['name']} {row['change_percent']:+.2f}%" for row in context.get("markets", []) if row.get("available")
        ) or "Reference markets unavailable"
        self.global_text.setText(
            f"GIFT Nifty: {gift_text} — {gift.get('source', 'NSE IX official')}\n"
            f"Global breadth: {context.get('breadth', 'UNAVAILABLE')} | TPS context: {context.get('bias', 'UNAVAILABLE')}\n"
            f"{references}\n{context.get('warning', '')}"
        )
        passed = "\n".join("PASS — " + item for item in result.get("passed", [])) or "No directional confirmation passed."
        failed = "\n".join("WAIT — " + item for item in result.get("blockers", [])) or "No remaining blocker."
        liquidity = result.get("option_liquidity") or {}
        spread = liquidity.get("spread_percent")
        liquidity_text = (f"{liquidity.get('symbol')} | LTP {liquidity.get('ltp', 0):.2f} | Bid/Ask "
                          f"{liquidity.get('bid', 0):.2f}/{liquidity.get('ask', 0):.2f} | "
                          f"Spread {f'{spread:.2f}%' if spread is not None else 'unavailable'} | {liquidity.get('status')}"
                          if liquidity.get("available") else liquidity.get("status", "Option liquidity unavailable"))
        premium_passed = "\n".join("OPTION PASS — " + item for item in liquidity.get("premium_passed", []))
        premium_failed = "\n".join("OPTION WAIT — " + item for item in liquidity.get("premium_blockers", []))
        self.evidence.setText(
            f"UNDERLYING/FUTURE DIRECTION EVIDENCE:\n{passed}\n{failed}\n\n"
            f"SELECTED OPTION PREMIUM EVIDENCE:\n{liquidity_text}\n{premium_passed}\n{premium_failed}\n\n{result['warning']}"
        )
        self.status.setText(
            f"{result['provider']} | Direction source {result['future_symbol']} completed {result['candle_time']} | "
            f"Option candle {result.get('option_candle_time', 'not selected')} | Future volume {result['volume_ratio']:.2f}x | Global {result['global_bias']}"
        )
        alert_key = (result.get("symbol"), result.get("candle_time"), result.get("action"))
        if result.get("published") and alert_key != self._last_alert:
            self._last_alert = alert_key; self.scalp_alert.emit(result)
        self._unlock()

    def show_error(self, message):
        self.status.setText(f"Scalper temporarily unavailable: {message}"); self._unlock()

    def _unlock(self):
        self._running = False; self.run.setEnabled(True)
