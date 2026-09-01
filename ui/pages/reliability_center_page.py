from datetime import datetime

from PySide6.QtWidgets import (
    QGridLayout, QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.market_session import IST, market_session
from core.settings_store import SettingsStore
from services.live_session import LiveSession
from services.market_data_hub import MarketDataHub
from services.reliability_intelligence import (
    data_quality_gate, execution_quality, missed_opportunities, shadow_eligibility,
    strategy_matrix, trade_timeline,
)
from ui.widgets.cards.dashboard_card import DashboardCard


class ReliabilityCenterPage(QWidget):
    """One evidence-led operator view; analysis only, no order submission."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(18, 16, 18, 22)
        title = QLabel("TPS Reliability Cockpit — Evidence, Missed Trades & Execution Quality")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Cutie saved evidence ko summarize karti hai. Model score ya scenario coverage guaranteed profit nahi hai; safety blockers yahan se bypass nahi hote.")
        note.setWordWrap(True); layout.addWidget(note)
        grid = QGridLayout()
        self.cards = {
            "gate": DashboardCard("Automatic Data-Quality Gate", "Waiting"),
            "shadow": DashboardCard("Shadow-Mode Eligibility", "Waiting"),
            "execution": DashboardCard("Execution Quality", "Waiting"),
            "missed": DashboardCard("Missed Opportunity Review", "Waiting"),
        }
        for i, card in enumerate(self.cards.values()): grid.addWidget(card, i // 2, i % 2)
        layout.addLayout(grid)
        refresh = QPushButton("Refresh Complete Reliability Audit"); refresh.clicked.connect(self.refresh); layout.addWidget(refresh)

        layout.addWidget(QLabel("Trade Decision Timeline — WATCH → READY → ENTRY/CAPTURE"))
        self.timeline = self._table(("Time", "Candle", "Index", "Side", "Stage", "Score", "Outcome", "Primary reason", "Delay"), 260)
        layout.addWidget(self.timeline)
        layout.addWidget(QLabel("Missed Opportunity Analyzer — replay shortlist, not entry permission"))
        self.missed = self._table(("Priority", "Time", "Index", "Side", "Score", "Checks", "Outcome", "Primary blocker", "Replay status"), 230)
        layout.addWidget(self.missed)
        layout.addWidget(QLabel("Strategy Performance Matrix — regime-wise observed outcomes"))
        self.matrix = self._table(("Strategy", "Family", "Regime", "Samples", "Days", "Win %", "95% lower", "Expectancy", "PF", "Drawdown", "Validation"), 260)
        layout.addWidget(self.matrix)
        scroll.setWidget(body); outer.addWidget(scroll); self.refresh()

    @staticmethod
    def _table(headers, height):
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers); table.setMinimumHeight(height)
        table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        return table

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values): table.setItem(r, c, QTableWidgetItem(str(value if value not in (None, "") else "-")))
        table.resizeColumnsToContents()

    def refresh(self):
        settings = SettingsStore().load()
        date = datetime.now(IST).strftime("%d-%m-%Y")
        gate = data_quality_gate(
            connected=LiveSession.connected(), market_state=market_session(settings=settings)["state"],
            hub_health=MarketDataHub.health(), broker_health=self.db.get_broker_health(limit=200),
        )
        shadow = shadow_eligibility(self.db); quality = execution_quality(self.db)
        missed = missed_opportunities(self.db, date); timeline = trade_timeline(self.db, date)
        self.cards["gate"].set_value(f"{gate['status']}\n{'; '.join(gate['reasons'][:2]) or 'Verified sources ready'}")
        self.cards["shadow"].set_value(f"{shadow['state']}\n{shadow['wins']}/{shadow['samples']} wins | lower {shadow['wilson_lower_bound']:.1f}%\nExpectancy ₹{shadow['expectancy']:,.2f}")
        self.cards["execution"].set_value(f"Verified fills {quality['verified_fills']}/{quality['real_submissions']}\nFill coverage {quality['fill_coverage']:.1f}% | Slippage {quality['slippage_status']}")
        self.cards["missed"].set_value(f"{len(missed)} replay candidate(s) today\nSafety locks remain active")
        self._fill(self.timeline, [(x['time'], x['candle'], x['symbol'], x['side'], x['stage'], x['score'], x['outcome'], x['reason'], x['delay']) for x in timeline])
        self._fill(self.missed, [(x['priority'], x['time'], x['symbol'], x['side'], x['score'], x['checks'], x['outcome'], x['blocker'], x['replay_status']) for x in missed])
        self._fill(self.matrix, [(x['strategy'], x['family'], x['regime'], x['samples'], x['independent_days'], f"{x['win_rate']:.1f}%", f"{x['lower_bound']:.1f}%", f"₹{x['expectancy']:,.2f}", x['profit_factor'], f"₹{x['drawdown']:,.2f}", x['tier']) for x in strategy_matrix(self.db)])
