"""VIX implied-move versus realised-movement decision support."""
from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from services.live_session import LiveSession
from services.option_strategy_service import OptionStrategyService
from ui.widgets.cards.dashboard_card import DashboardCard


class VolatilityIntelligencePage(QWidget):
    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(10)
        scroll.setWidget(content); outer.addWidget(scroll)

        title = QLabel("Volatility Intelligence — Implied Move vs Actual Move")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "TPS compares India VIX's one-standard-deviation daily move with the completed-candle session range, "
            "ATR and realised volatility. VIX describes movement potential, not direction. Direction still comes "
            "from EMA/VWAP/SuperTrend/price action/OI; volume measures strength and live Greeks/IV guide only a defined-risk strike or strategy review."
        )
        note.setWordWrap(True); layout.addWidget(note)

        controls = QGridLayout()
        self.index = QComboBox(); self.index.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.run = QPushButton("Load Live Volatility Comparison")
        self.run.clicked.connect(self.analyze)
        controls.addWidget(self.index, 0, 0); controls.addWidget(self.run, 0, 1)
        layout.addLayout(controls)
        self.status = QLabel("Connect a supported broker, then load completed live candles, VIX history and option-chain context.")
        self.status.setWordWrap(True); layout.addWidget(self.status)

        cards = QGridLayout(); cards.setHorizontalSpacing(9); cards.setVerticalSpacing(9)
        self.cards = {key: DashboardCard(label, "-") for key, label in (
            ("expected", "VIX Expected Move Today"), ("actual", "Actual Movement So Far"),
            ("utilized", "Expected Range Utilized"), ("vix", "VIX Trend / Historical Regime"),
            ("atr", "ATR / Realised Volatility"), ("direction", "Direction / Strength"),
            ("strategy", "Strike / Defined-Risk Strategy"), ("budget", "Remaining Movement Budget"),
        )}
        for position, card in enumerate(self.cards.values()):
            card.set_compact(True); card.setMinimumHeight(105)
            cards.addWidget(card, position // 4, position % 4)
        layout.addLayout(cards)

        evidence_box = QGroupBox("Complete evidence and interpretation")
        evidence_layout = QVBoxLayout(evidence_box)
        self.evidence = QLabel("No live comparison has run yet.")
        self.evidence.setWordWrap(True); evidence_layout.addWidget(self.evidence)
        layout.addWidget(evidence_box)
        caution = QLabel(
            "Safety: Expected move is a statistical estimate, not a price target or guaranteed boundary. "
            "Range utilization cannot by itself justify CE/PE buying or option selling. Verify expiry, liquidity, bid/ask spread, event risk and maximum defined loss."
        )
        caution.setWordWrap(True); layout.addWidget(caution); layout.addStretch()
        self.loaded.connect(self.show_result); self.failed.connect(self.show_error)
        self.running = False

    def analyze(self):
        if self.running:
            return
        if not LiveSession.connected():
            self.status.setText("Broker data is not connected. Open Settings and connect read-only live data first.")
            return
        self.running = True; self.run.setEnabled(False)
        symbol = self.index.currentText()
        self.status.setText(f"Loading {symbol} completed candles, 1-year India VIX history and option-chain evidence...")
        Thread(target=self._worker, args=(symbol,), daemon=True).start()

    def _worker(self, symbol):
        try:
            self.loaded.emit(OptionStrategyService(LiveSession.client).analyze(symbol))
        except (RuntimeError, ValueError, KeyError, TypeError, IndexError) as error:
            self.failed.emit(str(error))

    @staticmethod
    def _number(value, suffix=""):
        return f"{float(value):,.2f}{suffix}" if value is not None else "Unavailable"

    def show_result(self, result):
        environment = result.get("environment") or {}
        expected = environment.get("expected_daily_range")
        actual = environment.get("actual_movement_so_far")
        utilized = environment.get("expected_range_utilized_percent")
        remaining = environment.get("remaining_expected_range")
        percentile = environment.get("vix_percentile")
        percentile_text = f"P{percentile:.1f}" if percentile is not None else "fallback (history insufficient)"
        trend_change = environment.get("vix_trend_percent")
        trend_change_text = f"{trend_change:+.2f}% vs 5-day mean" if trend_change is not None else "trend unavailable"
        self.cards["expected"].set_value(f"±{self._number(expected, ' pts')}\n1σ VIX estimate")
        self.cards["actual"].set_value(f"{self._number(actual, ' pts')}\nSession high − low")
        self.cards["utilized"].set_value(
            f"{self._number(utilized, '%')}\n{environment.get('movement_state', 'UNAVAILABLE')}"
        )
        self.cards["vix"].set_value(
            f"{self._number(environment.get('vix'))} | {environment.get('vix_trend', 'UNAVAILABLE')}\n"
            f"{environment.get('vix_historical_regime', 'UNAVAILABLE')} ({percentile_text})"
        )
        realized = environment.get("realized_volatility_annualized")
        self.cards["atr"].set_value(
            f"ATR14 {self._number(environment.get('atr_points'), ' pts')} ({self._number(environment.get('atr_percent'), '%')})\n"
            f"Realised vol {self._number(realized, '% annualised')}"
        )
        self.cards["direction"].set_value(
            f"{result.get('bias', 'UNAVAILABLE')}\nVolume {environment.get('volume_regime', 'UNAVAILABLE')}"
        )
        self.cards["strategy"].set_value(
            f"{result.get('state', 'WAIT')}\n{result.get('strategy', 'No clean structure')}"
        )
        self.cards["budget"].set_value(
            f"{self._number(remaining, ' pts')}\n{('Available' if environment.get('regular_move_available') else 'Consumed / constrained')}"
        )
        chain = result.get("chain") or {}
        warnings = "; ".join(environment.get("warnings") or []) or "None"
        reasons = "\n• ".join(result.get("reasons") or [])
        self.evidence.setText(
            f"VIX history: {environment.get('vix_history_samples', 0)} daily sample(s); classification source: {environment.get('vix_regime_source', 'unavailable')}. "
            f"VIX trend: {trend_change_text}.\n\n"
            f"Direction stack: {result.get('bias')} | OI-PCR {chain.get('pcr_oi') if chain.get('pcr_oi') is not None else 'unavailable'} | "
            f"Put support {chain.get('put_support') or '-'} | Call resistance {chain.get('call_resistance') or '-'}.\n"
            f"Option movement context: ATM straddle expected move {chain.get('expected_move') or '-'} | "
            f"Focused max pain {chain.get('focused_max_pain') or '-'} | Chain quality {chain.get('data_quality', 0)}/100.\n\n"
            f"Evidence:\n• {reasons}\n\nWarnings: {warnings}"
        )
        self.status.setText(
            f"{result.get('symbol')} volatility comparison ready from completed candle {result.get('candle_time')}. No broker order placed."
        )
        self.running = False; self.run.setEnabled(True)

    def show_error(self, message):
        self.status.setText(f"Volatility comparison unavailable: {message}")
        self.running = False; self.run.setEnabled(True)
