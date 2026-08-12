from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.option_strategy_service import OptionStrategyService
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
        self.status = QLabel("Connect Angel One and analyze an index. TPS may return WAIT when no clean hedged payoff exists.")
        self.status.setWordWrap(True); layout.addWidget(self.status)

        cards = QGridLayout()
        self.cards = {key: DashboardCard(label, "-") for key, label in (
            ("strategy", "Suggested Structure"), ("bias", "Market Bias"), ("environment", "VIX / Regime"),
            ("range", "Expected / Remaining Range"), ("payoff", "One-Lot Max Profit / Loss"), ("target", "Regular-Move Objective"),
        )}
        for i, card in enumerate(self.cards.values()):
            card.set_compact(True); cards.addWidget(card, i // 3, i % 3)
        layout.addLayout(cards)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Action", "Type", "Strike", "Contract", "Price", "Lots", "Quantity"))
        self.table.setMinimumHeight(180); self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
        self.details = QLabel("No strategy analysis has run yet."); self.details.setWordWrap(True); layout.addWidget(self.details)
        layout.addStretch()
        self.timer = QTimer(self); self.timer.setInterval(300_000); self.timer.timeout.connect(self.analyze)
        self.running = False; self.loaded.connect(self.show_result); self.failed.connect(self.show_error)

    def toggle_auto(self, enabled):
        if enabled:
            self.timer.start(); self.analyze()
        else:
            self.timer.stop(); self.status.setText("Automatic strategy monitoring disabled; manual analysis remains available.")

    def analyze(self):
        if self.running:
            return
        if not LiveSession.connected():
            self.status.setText("Angel One is not connected. Connect it from Settings first.")
            return
        self.running = True; self.run.setEnabled(False)
        symbol = self.index.currentText(); self.status.setText(f"Analyzing {symbol} completed candles, VIX and live defined-risk spreads...")
        Thread(target=self._worker, args=(symbol,), daemon=True).start()

    def _worker(self, symbol):
        try:
            self.loaded.emit(OptionStrategyService(LiveSession.client).analyze(symbol))
        except (RuntimeError, ValueError, KeyError, TypeError, IndexError) as error:
            self.failed.emit(str(error))

    def show_result(self, result):
        self.cards["strategy"].set_value(f"{result['state']}\n{result['strategy']}")
        self.cards["bias"].set_value(f"{result['bias']}\nConfidence {result.get('confidence', 0)}%")
        self.cards["environment"].set_value(f"VIX {result.get('vix') or 'Unavailable'}\n{result['regime']}")
        expected, remaining = result.get("expected_daily_range"), result.get("remaining_expected_range")
        self.cards["range"].set_value(f"Expected {expected if expected is not None else '-'}\nRemaining {remaining if remaining is not None else '-'} points")
        if result.get("max_loss") is not None:
            self.cards["payoff"].set_value(f"Profit Rs {result['max_profit']:,.2f}\nLoss Rs {result['max_loss']:,.2f}")
        else:
            self.cards["payoff"].set_value("No valid payoff yet")
        self.cards["target"].set_value(f"{result.get('regular_move_target_points') or '-'} underlying points\nEnvironment-adaptive")
        legs = result.get("legs") or []; self.table.setRowCount(len(legs))
        for row_index, leg in enumerate(legs):
            values = (leg["action"], leg["option_type"], f"{leg['strike']:,.0f}", leg["symbol"], f"{leg['price']:,.2f}", leg["lots"], leg["quantity"])
            for column, value in enumerate(values): self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents(); self.table.horizontalHeader().setStretchLastSection(True)
        reasons = "\n- ".join(result.get("reasons") or [])
        blockers = "\n- ".join(result.get("blockers") or [])
        payoff = f"Net {result.get('net_type')} {result.get('net_premium')} | Breakeven(s): {result.get('breakevens')}" if result.get("net_type") else "No tradeable defined-risk payoff is ready."
        greeks = result.get("portfolio_greeks_estimate")
        greek_text = (
            f"\nEstimated portfolio Greeks (whole position): Delta {greeks['delta']} | Gamma {greeks['gamma']} | "
            f"Theta/day {greeks['theta_per_day']} | Vega/1% {greeks['vega_per_1pct']}"
            if greeks else "\nPortfolio Greeks unavailable because expiry/premium inputs were incomplete."
        )
        self.details.setText(
            f"Completed candle: {result['candle_time']} | Expiry: {result['expiry']} | {result['quoted_contracts']} live contracts quoted\n"
            f"{payoff}{greek_text}\nEvidence:\n- {reasons}"
            + (f"\nBlockers:\n- {blockers}" if blockers else "")
            + f"\n\n{result['warning']}"
        )
        self.status.setText(f"{result['symbol']} analysis complete: {result['state']}. No broker order placed.")
        self.running = False; self.run.setEnabled(True)

    def show_error(self, message):
        self.status.setText(f"Option strategy analysis unavailable: {message}")
        self.running = False; self.run.setEnabled(True)
