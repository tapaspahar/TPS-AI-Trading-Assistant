from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.settings_store import SettingsStore
from engine.risk_engine import RiskEngine
from ui.widgets.cards.dashboard_card import DashboardCard


class RiskPage(QWidget):
    """Whole-lot option risk control centre. It never places an order."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        self.layout = QVBoxLayout(content)
        self.layout.setContentsMargins(18, 16, 18, 18)
        self.layout.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        title = QLabel("Risk Control Center")
        title.setObjectName("pageTitle")
        self.layout.addWidget(title)
        subtitle = QLabel("Check whole-lot option risk, daily capacity and safety limits before any manual decision.")
        subtitle.setWordWrap(True)
        self.layout.addWidget(subtitle)

        cards = QGridLayout()
        cards.setSpacing(10)
        self.cards = {}
        for index, (key, label) in enumerate((
            ("capital", "Account Capital"), ("trade_cap", "Per-Trade Risk Cap"),
            ("daily_remaining", "Daily Loss Capacity"), ("trades", "Trades Today"),
        )):
            card = DashboardCard(label, "—")
            card.set_compact(True)
            self.cards[key] = card
            cards.addWidget(card, index // 2, index % 2)
        self.layout.addLayout(cards)

        plan_box = QGroupBox("Plan under review")
        form = QFormLayout(plan_box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.contract = QLineEdit("Manual option plan")
        self.contract.setReadOnly(True)
        self.entry, self.stoploss, self.target = QLineEdit(), QLineEdit(), QLineEdit()
        self.lot_size = QSpinBox()
        self.lot_size.setRange(1, 10000)
        self.lot_size.setValue(65)
        self.requested_lots = QSpinBox()
        self.requested_lots.setRange(1, 100)
        for label, field in (
            ("Contract", self.contract), ("Entry premium", self.entry),
            ("Stop loss", self.stoploss), ("Target", self.target),
            ("Exchange lot size", self.lot_size), ("Planned lots", self.requested_lots),
        ):
            form.addRow(label, field)
        self.layout.addWidget(plan_box)

        buttons = QGridLayout()
        analyze = QPushButton("Analyze Risk Controls")
        analyze.clicked.connect(self.calculate)
        refresh = QPushButton("Refresh Daily Limits")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(analyze, 0, 0)
        buttons.addWidget(refresh, 0, 1)
        self.layout.addLayout(buttons)

        result_box = QGroupBox("Control verdict")
        result_layout = QVBoxLayout(result_box)
        self.verdict = QLabel("Enter a plan or create one in Options Workspace.")
        self.verdict.setObjectName("pageTitle")
        self.verdict.setWordWrap(True)
        self.details = QLabel("TPS only evaluates risk. It cannot place, modify or cancel an order.")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        result_layout.addWidget(self.verdict)
        result_layout.addWidget(self.details)
        self.layout.addWidget(result_box)
        self.layout.addStretch()
        self.refresh()

    def _daily_state(self):
        today = datetime.now().strftime("%d-%m-%Y")
        db = Database()
        progress = db.paper_trade_progress(today)
        realized_pnl = sum(float(row["pnl"] or 0) for row in db.get_journal_rows()
                           if row["trade_date"] == today and row["status"] == "CLOSED")
        db.close()
        return progress, realized_pnl

    def refresh(self):
        self.settings = SettingsStore().load()
        self.progress, self.realized_pnl = self._daily_state()
        capital = float(self.settings["capital"])
        trade_cap = capital * float(self.settings["risk_percent"]) / 100
        daily_limit = capital * float(self.settings["daily_loss_percent"]) / 100
        daily_remaining = max(0, daily_limit - max(0, -self.realized_pnl))
        self.cards["capital"].set_value(f"₹{capital:,.0f}")
        self.cards["trade_cap"].set_value(f"₹{trade_cap:,.0f} ({self.settings['risk_percent']}%)")
        self.cards["daily_remaining"].set_value(f"₹{daily_remaining:,.0f} of ₹{daily_limit:,.0f}")
        self.cards["trades"].set_value(f"{self.progress['trades']} / {self.settings['max_trades_per_day']}")

    def load_trade_plan(self, plan: dict):
        contract = plan.get("contract", {})
        self.contract.setText(str(contract.get("symbol") or plan.get("underlying") or "Option plan"))
        self.entry.setText(str(plan.get("entry", "")))
        self.stoploss.setText(str(plan.get("stoploss", "")))
        self.target.setText(str(plan.get("target", "")))
        self.lot_size.setValue(max(1, int(plan.get("lot_size", contract.get("lot_size", 1)) or 1)))
        self.requested_lots.setValue(max(1, int(plan.get("lots", 1) or 1)))
        self.calculate()

    def calculate(self):
        try:
            self.refresh()
            result = RiskEngine().assess_option_risk(
                capital=float(self.settings["capital"]), risk_percent=float(self.settings["risk_percent"]),
                daily_loss_percent=float(self.settings["daily_loss_percent"]),
                max_trades_per_day=int(self.settings["max_trades_per_day"]),
                trades_today=self.progress["trades"], open_trades=self.progress["open_trades"],
                realized_pnl=self.realized_pnl, entry=float(self.entry.text()),
                stoploss=float(self.stoploss.text()), target=float(self.target.text()),
                lot_size=self.lot_size.value(), requested_lots=self.requested_lots.value(),
            )
            colour = {"SAFE": "#48e0a4", "REVIEW": "#ffd166", "REDUCE LOTS": "#ff9f43", "BLOCKED": "#ff6b6b"}[result["verdict"]]
            self.verdict.setText(f"{result['verdict']} — {self.contract.text()}")
            self.verdict.setStyleSheet(f"color: {colour};")
            reasons = "; ".join(result["blockers"]) if result["blockers"] else "No daily safety limit is blocking this plan."
            self.details.setText(
                f"Planned quantity: {result['quantity']} ({self.requested_lots.value()} lot(s))\n"
                f"Stop-loss risk: ₹{result['risk_per_unit']:,.2f} per unit | ₹{result['risk_per_lot']:,.2f} per lot\n"
                f"Planned maximum loss: ₹{result['planned_risk']:,.2f} | Maximum safe lots: {result['safe_lots']}\n"
                f"Risk:Reward: 1:{result['rr_ratio']:.2f} | Daily loss capacity left: ₹{result['daily_remaining']:,.2f}\n"
                f"Safety check: {reasons}\n\nTPS only evaluates risk. It cannot place, modify or cancel an order."
            )
        except (TypeError, ValueError):
            self.verdict.setText("INPUT REQUIRED")
            self.verdict.setStyleSheet("color: #ffd166;")
            self.details.setText("Enter valid positive prices. For option buying, stop loss must be below entry and target above entry.")
