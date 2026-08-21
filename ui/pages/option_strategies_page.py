from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.option_strategy_service import OptionStrategyService
from engine.strategy_adjustment_engine import monitor_strategy_plan
from core.settings_store import SettingsStore
from core.assistant_voice import cutie_says
from services.notification_service import NotificationService
from ui.widgets.cards.dashboard_card import DashboardCard


class OptionStrategiesPage(QWidget):
    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(10)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Option Strategies"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "TPS uses India VIX for expected movement magnitude (not direction), then combines completed 5-minute index-future candles, live option prices and OI zones to suggest only a defined-risk structure. "
            "REVIEW CANDIDATE is not guaranteed income and never places a broker order."
        )
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.run = QPushButton("Analyze Limited-Risk Strategy Now"); self.run.clicked.connect(self.analyze)
        self.auto = QCheckBox("Monitor every 5 minutes (review suggestions only)"); self.auto.toggled.connect(self.toggle_auto)
        controls.addWidget(self.index, 0, 0); controls.addWidget(self.run, 0, 1); controls.addWidget(self.auto, 1, 0, 1, 2)
        layout.addLayout(controls)
        plan_controls = QGridLayout()
        self.start_plan = QPushButton("Save Current Suggestion & Monitor Adjustments")
        self.start_plan.clicked.connect(self.start_plan_monitor)
        self.start_plan.setEnabled(False)
        self.stop_plan = QPushButton("Stop Saved-Plan Monitor")
        self.stop_plan.clicked.connect(self.stop_plan_monitor)
        self.stop_plan.setEnabled(False)
        plan_controls.addWidget(self.start_plan, 0, 0)
        plan_controls.addWidget(self.stop_plan, 0, 1)
        layout.addLayout(plan_controls)
        self.status = QLabel(cutie_says("Broker connect karke index analyze kijiye. Clean hedged payoff na mile to main WAIT bataungi."))
        self.status.setWordWrap(True); layout.addWidget(self.status)

        cards = QGridLayout()
        self.cards = {key: DashboardCard(label, "-") for key, label in (
            ("strategy", "Suggested Structure"), ("bias", "Market Bias"), ("environment", "VIX / Regime"),
            ("range", "Expected / Remaining Range"), ("payoff", "Target Profit / Max Defined Loss"), ("target", "Expiry / Candidate Side"),
        )}
        for i, card in enumerate(self.cards.values()):
            card.set_compact(True); cards.addWidget(card, i // 3, i % 3)
        layout.addLayout(cards)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Action", "Type", "Strike", "Contract", "Price", "Lots", "Quantity"))
        self.table.setMinimumHeight(180); self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
        self.details = QLabel("No strategy analysis has run yet."); self.details.setWordWrap(True); layout.addWidget(self.details)
        self.monitor_status = QLabel(
            cutie_says("Abhi koi active strategy save nahi hai. REVIEW CANDIDATE save kijiye; main har 5-minute evidence par strategy health aur adjustment bataungi.")
        )
        self.monitor_status.setWordWrap(True); layout.addWidget(self.monitor_status)
        self.adjustments = QTableWidget(0, 6)
        self.adjustments.setHorizontalHeaderLabels(("Step", "Action", "Type", "Strike", "Contract", "Why"))
        self.adjustments.setMinimumHeight(145); self.adjustments.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.adjustments)
        layout.addStretch()
        self.timer = QTimer(self); self.timer.setInterval(300_000); self.timer.timeout.connect(self.analyze)
        self.running = False; self.last_result = None; self.last_monitor_state = None
        self.settings_store = SettingsStore()
        self.active_plan = self.settings_store.load().get("active_option_strategy_plan") or None
        self.loaded.connect(self.show_result); self.failed.connect(self.show_error)
        if self.active_plan:
            saved_index = self.index.findText(str(self.active_plan.get("symbol") or "NIFTY"))
            if saved_index >= 0: self.index.setCurrentIndex(saved_index)
            self.stop_plan.setEnabled(True)
            self.monitor_status.setText(
                f"Restored saved {self.active_plan.get('strategy')} monitor from spot {float(self.active_plan.get('spot') or 0):,.2f}. "
                "It will resume after broker data connects."
            )
            self.auto.setChecked(True)

    @staticmethod
    def _saved_plan(result):
        keep = ("symbol", "strategy", "spot", "net_type", "net_premium", "expected_daily_range", "breakevens", "expiry", "candidate_side", "management_reference")
        plan = {key: result.get(key) for key in keep}
        plan["legs"] = [
            {key: leg.get(key) for key in ("action", "option_type", "strike", "symbol", "price", "lots", "lot_size", "quantity")}
            for leg in (result.get("legs") or [])
        ]
        return plan

    def _persist_plan(self, plan):
        values = self.settings_store.load()
        values["active_option_strategy_plan"] = plan
        self.settings_store.save(values)

    def start_plan_monitor(self):
        if not self.last_result or self.last_result.get("state") != "REVIEW CANDIDATE":
            self.monitor_status.setText("Only a live REVIEW CANDIDATE with complete defined-risk legs can be saved for monitoring.")
            return
        self.active_plan = self._saved_plan(self.last_result)
        self.last_monitor_state = None
        self._persist_plan(self.active_plan)
        self.stop_plan.setEnabled(True)
        self.auto.setChecked(True)
        self.monitor_status.setText(
            f"Monitoring saved {self.active_plan['strategy']} from spot {self.active_plan['spot']:,.2f}. "
            "Fresh completed-candle evidence will be checked every 5 minutes."
        )

    def stop_plan_monitor(self):
        self.active_plan = None; self.last_monitor_state = None; self._persist_plan(None); self.stop_plan.setEnabled(False)
        self.adjustments.setRowCount(0)
        self.monitor_status.setText(cutie_says("Strategy monitor band hai. Maine koi broker order place ya change nahi kiya."))

    def toggle_auto(self, enabled):
        if enabled:
            self.timer.start(); self.analyze()
        else:
            self.timer.stop(); self.status.setText(cutie_says("Automatic strategy monitoring band hai; manual analysis available hai."))

    def analyze(self):
        if self.running:
            return
        if not LiveSession.connected():
            self.status.setText(cutie_says("Broker data connected nahi hai. Pehle Settings se supported broker connect kijiye."))
            return
        self.running = True; self.run.setEnabled(False)
        symbol = self.index.currentText(); self.status.setText(cutie_says(f"Main {symbol} ke completed candles, VIX aur live defined-risk spreads analyze kar rahi hoon..."))
        Thread(target=self._worker, args=(symbol,), daemon=True).start()

    def _worker(self, symbol):
        try:
            self.loaded.emit(OptionStrategyService(LiveSession.client).analyze(symbol))
        except (RuntimeError, ValueError, KeyError, TypeError, IndexError) as error:
            self.failed.emit(str(error))

    def show_result(self, result):
        self.last_result = result
        self.cards["strategy"].set_value(f"{result['state']}\n{result['strategy']}")
        self.cards["bias"].set_value(f"{result['bias']}\nConfidence {result.get('confidence', 0)}%")
        environment = result.get("environment") or {}
        percentile = environment.get("vix_percentile")
        percentile_text = f"P{percentile:.1f}" if percentile is not None else "fallback"
        self.cards["environment"].set_value(
            f"VIX {result.get('vix') or 'Unavailable'} | {environment.get('vix_trend', 'UNAVAILABLE')}\n"
            f"{environment.get('vix_historical_regime', result['regime'])} ({percentile_text})"
        )
        expected, remaining = result.get("expected_daily_range"), result.get("remaining_expected_range")
        low, high = result.get("vix_expected_low"), result.get("vix_expected_high")
        range_text = f"{low:,.2f} to {high:,.2f}" if low is not None and high is not None else "VIX range unavailable"
        utilized = environment.get("expected_range_utilized_percent")
        utilization_text = f" | Used {utilized:.1f}%" if utilized is not None else ""
        self.cards["range"].set_value(
            f"{range_text}\nRemaining {remaining if remaining is not None else '-'} points{utilization_text}"
        )
        if result.get("max_loss") is not None:
            management = result.get("management_reference") or {}
            self.cards["payoff"].set_value(
                f"Target Rs {float(management.get('target_profit') or 0):,.2f}\nMax loss Rs {result['max_loss']:,.2f}"
            )
        else:
            self.cards["payoff"].set_value("No valid payoff yet")
        self.cards["target"].set_value(f"{result.get('expiry') or '-'}\n{result.get('candidate_side') or '-'} defined-risk")
        legs = result.get("legs") or []; self.table.setRowCount(len(legs))
        for row_index, leg in enumerate(legs):
            values = (leg["action"], leg["option_type"], f"{leg['strike']:,.0f}", leg["symbol"], f"{leg['price']:,.2f}", leg["lots"], leg["quantity"])
            for column, value in enumerate(values): self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents(); self.table.horizontalHeader().setStretchLastSection(True)
        reasons = "\n- ".join(result.get("reasons") or [])
        blockers = "\n- ".join(result.get("blockers") or [])
        payoff = f"Net {result.get('net_type')} {result.get('net_premium')} | Breakeven(s): {result.get('breakevens')}" if result.get("net_type") else "No tradeable defined-risk payoff is ready."
        management = result.get("management_reference") or {}
        management_text = (
            f"\nPaper management: target profit Rs {float(management.get('target_profit') or 0):,.2f} "
            f"({management.get('target_profit_percent_of_max') or '-'}% of maximum potential profit) | "
            f"loss-review at Rs {float(management.get('loss_review_amount') or 0):,.2f} | "
            f"defined maximum loss Rs {float(management.get('defined_max_loss') or 0):,.2f}. Not guaranteed."
            if management else ""
        )
        greeks = result.get("portfolio_greeks_estimate")
        greek_text = (
            f"\nEstimated portfolio Greeks (whole position): Delta {greeks['delta']} | Gamma {greeks['gamma']} | "
            f"Theta/day {greeks['theta_per_day']} | Vega/1% {greeks['vega_per_1pct']}"
            if greeks else "\nPortfolio Greeks unavailable because expiry/premium inputs were incomplete."
        )
        self.details.setText(
            f"Completed candle: {result['candle_time']} | Expiry: {result['expiry']} | {result['quoted_contracts']} live contracts quoted\n"
            f"{payoff}{management_text}{greek_text}\nEvidence:\n- {reasons}"
            + (f"\nBlockers:\n- {blockers}" if blockers else "")
            + f"\n\n{result['warning']}"
        )
        self.status.setText(cutie_says(f"{result['symbol']} analysis complete hai: {result['state']}. Maine koi broker order place nahi kiya."))
        self.start_plan.setEnabled(result.get("state") == "REVIEW CANDIDATE" and bool(result.get("legs")))
        if self.active_plan:
            self.show_monitor_result(monitor_strategy_plan(self.active_plan, result))
        self.running = False; self.run.setEnabled(True)

    def show_monitor_result(self, monitor):
        pnl = monitor.get("estimated_pnl")
        pnl_text = f" | Estimated executable P&L Rs {pnl:,.2f}" if pnl is not None else " | P&L unavailable (quotes incomplete)"
        self.monitor_status.setText(
            cutie_says(f"{monitor['decision']} | Strategy health {monitor['strategy_health']}/100 | Spot {monitor['spot']:,.2f} | Fresh bias {monitor['fresh_bias']}{pnl_text}") + "\n"
            f"{monitor['reason']}"
            + (f"\nConfirmed transition: {monitor['transition']} | Replacement: {monitor.get('replacement_strategy')} | Expiry: {monitor.get('replacement_expiry')}" if monitor.get("transition") else "")
            + (f"\nReplacement reference: target Rs {float(monitor.get('replacement_target_profit') or 0):,.2f} | max defined loss Rs {float(monitor.get('replacement_max_loss') or 0):,.2f}" if monitor.get("replacement_strategy") else "")
            + f"\n{monitor['warning']}"
        )
        actions = monitor.get("actions") or []; self.adjustments.setRowCount(len(actions))
        for row, action in enumerate(actions):
            values = (action["step"], action["action"], action["option_type"], f"{float(action['strike']):,.0f}", action["symbol"], action["reason"])
            for column, value in enumerate(values): self.adjustments.setItem(row, column, QTableWidgetItem(str(value)))
        self.adjustments.resizeColumnsToContents(); self.adjustments.horizontalHeader().setStretchLastSection(True)
        if monitor["state"] != self.last_monitor_state and monitor["state"] in {"WATCH", "EXIT / REASSESS"}:
            NotificationService.instance().notify(
                "option_strategies", f"Cutie strategy alert — {monitor['decision']}",
                f"Cutie keh rahi hai: {self.active_plan.get('symbol')} {self.active_plan.get('strategy')}: {monitor['reason']}",
                dedupe_key=f"{self.active_plan.get('symbol')}:{self.active_plan.get('strategy')}:{monitor['decision']}",
                once_per_day=True,
            )
        self.last_monitor_state = monitor["state"]

    def show_error(self, message):
        self.status.setText(cutie_says(f"Option strategy analysis abhi unavailable hai: {message}"))
        self.running = False; self.run.setEnabled(True)
