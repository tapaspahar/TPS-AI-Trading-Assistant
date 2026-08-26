import json
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.market_session import market_session
from core.settings_store import SettingsStore
from engine.strategy_portfolio_engine import build_strategy_catalog


def capturable_strategy_candidates(catalog, remaining):
    """Return only eligible candidates aligned with the current market evidence."""
    return [
        candidate for candidate in catalog
        if candidate.get("eligible") and candidate.get("market_alignment")
    ][:max(0, int(remaining or 0))]


class StrategyTradesPage(QWidget):
    """Automatic, multi-leg defined-risk paper validation ledger."""

    strategy_event = Signal(dict)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings = SettingsStore()
        self.latest_catalog = []
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(18, 16, 18, 22); layout.setSpacing(10)
        scroll.setWidget(body); outer.addWidget(scroll)

        title = QLabel("Strategy Trades — Captured Multi-Leg Performance")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Live defined-risk analysis aur VIX/ATR intelligence Option Strategies page par hai. Yeh page sirf "
            "automatically captured strategy trades, unke saved scores, outcomes aur actual closed-paper win-rate "
            "ranking dikhata hai. Top-performing strategy sabse upar rahegi; koi broker order place nahi hota."
        )
        intro.setWordWrap(True); layout.addWidget(intro)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Strategy Trades"); refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh); layout.addLayout(controls)
        self.summary = QLabel("Waiting for Option Strategies analysis..."); self.summary.setWordWrap(True); layout.addWidget(self.summary)

        performance_title = QLabel("Strategy ranking — actual closed paper win rate (top rank first)")
        performance_title.setObjectName("sectionTitle"); layout.addWidget(performance_title)
        self.performance = QTableWidget(0, 9)
        self.performance.setHorizontalHeaderLabels(("Rank", "Cutie name / structure", "Closed trades", "Wins", "Win rate", "Average P&L", "Total P&L", "Avg capture ROC", "Observed regimes"))
        self.performance.setEditTriggers(QTableWidget.NoEditTriggers); self.performance.setMinimumHeight(220)
        layout.addWidget(self.performance)

        ledger_title = QLabel("Captured strategy trades — automatic result history")
        ledger_title.setObjectName("sectionTitle"); layout.addWidget(ledger_title)
        self.ledger = QTableWidget(0, 17)
        self.ledger.setHorizontalHeaderLabels(("Date/time", "Index", "Cutie name", "Structure", "Capture score", "Scenario score", "Regime", "Bias", "Entry spot", "Last spot", "Payoff risk reserve", "Max benefit", "Max loss", "Model P&L", "Status", "Outcome", "Expiry"))
        self.ledger.setEditTriggers(QTableWidget.NoEditTriggers); self.ledger.setMinimumHeight(310)
        self.ledger.itemSelectionChanged.connect(self._ledger_detail)
        layout.addWidget(self.ledger)
        self.details = QLabel("Captured trade select karke every leg, saved score, payoff zone aur outcome explanation dekhiye.")
        self.details.setWordWrap(True); self.details.setMinimumHeight(110); layout.addWidget(self.details)
        layout.addStretch(); self.refresh()

    def ingest_analysis(self, result: dict):
        """Receive the same completed-candle evidence used by Option Strategies."""
        try:
            self.latest_catalog = build_strategy_catalog(result, self.settings.load())
            symbol = str(result.get("symbol") or "").upper()
            spot = float(result.get("spot") or 0)
            quote_rows = (result.get("chain") or {}).get("quote_rows") or []
            closed = self.db.update_strategy_trades(symbol, spot, str(result.get("candle_time") or ""), quote_rows) if symbol and spot else []
            session = market_session(settings=self.settings.load())
            captured = []
            if session.get("state") == "OPEN":
                today = datetime.now().strftime("%d-%m-%Y")
                used = len(self.db.get_strategy_trades(today, 100))
                remaining = max(0, 30 - used)
                source = dict(result)
                source.update({
                    "symbol": symbol,
                    "spot": spot,
                    "market_regime": str(
                        result.get("market_regime")
                        or (result.get("environment") or {}).get("regime")
                        or result.get("bias")
                        or "UNKNOWN"
                    ).upper(),
                })
                for candidate in capturable_strategy_candidates(self.latest_catalog, remaining):
                    trade_id = self.db.save_strategy_trade(candidate, source)
                    if trade_id:
                        captured.append(candidate.get("friendly_name") or candidate["strategy"])
            for name in captured:
                self.strategy_event.emit({"kind": "CAPTURED", "symbol": symbol, "strategy": name})
            for item in closed:
                self.strategy_event.emit({"kind": "CLOSED", "symbol": symbol, **item})
            self.refresh()
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            self.summary.setText(f"Strategy paper validation unavailable: {error}")

    def refresh(self):
        rows = self.db.get_strategy_trades(limit=1000)
        summary = self.db.get_strategy_trade_summary()
        self.ledger.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (
                f"{item['trade_date']} {str(item['captured_at'])[11:19]}", item["symbol"],
                item["friendly_name"] or item["strategy_name"], item["strategy_name"],
                f"{float(item['rank_score'] or 0):.0f}/100", f"{float(item['scenario_win_rate'] or 0):.0f}%",
                item["market_regime"] or "UNKNOWN", item["bias"],
                f"{float(item['entry_spot']):,.2f}", f"{float(item['last_spot']):,.2f}", f"₹{float(item['capital_required']):,.0f} risk",
                f"₹{float(item['max_profit']):,.0f}", f"₹{float(item['max_loss']):,.0f}", f"₹{float(item['current_pnl']):,.0f}", item["status"], item["outcome"], item["expiry"],
            )
            for column, value in enumerate(values): self.ledger.setItem(row, column, QTableWidgetItem(str(value)))
            self.ledger.item(row, 0).setData(256, int(item["id"]))
        self.ledger.resizeColumnsToContents(); self.ledger.horizontalHeader().setStretchLastSection(True)
        performance = self.db.get_strategy_performance()
        self.performance.setRowCount(len(performance))
        for row, item in enumerate(performance):
            samples = int(item["samples"] or 0); wins = int(item["wins"] or 0)
            values = (row + 1, f"{item['friendly_name']} / {item['strategy_name']}", samples, wins,
                      f"{float(item['win_rate'] or 0):.1f}%",
                      f"₹{float(item['average_pnl'] or 0):,.2f}", f"₹{float(item['total_pnl'] or 0):,.2f}",
                      f"{float(item['average_model_roc'] or 0):.1f}%", item["market_regimes"] or "UNKNOWN")
            for column, value in enumerate(values): self.performance.setItem(row, column, QTableWidgetItem(str(value)))
        self.performance.resizeColumnsToContents(); self.performance.horizontalHeader().setStretchLastSection(True)
        total = int(summary.get("total") or 0); closed = int(summary.get("closed_count") or 0); wins = int(summary.get("wins") or 0)
        self.summary.setText(
            f"Paper strategies: {total} | Open: {int(summary.get('open_count') or 0)} | Closed: {closed} | "
            f"Positive model outcomes: {wins}/{closed if closed else 0} | Realized model P&L: ₹{float(summary.get('pnl') or 0):,.2f}. "
            "Ranking sirf closed paper outcomes ke win rate par hai (tie me zyada samples, phir total P&L). "
            "Release 1.4.6 testing cap: 30 unique multi-strike strategy captures/day."
        )

    def _ledger_detail(self):
        row = self.ledger.currentRow()
        if row < 0 or not self.ledger.item(row, 0): return
        trade_id = self.ledger.item(row, 0).data(256)
        record = next((x for x in self.db.get_strategy_trades(limit=5000) if int(x["id"]) == int(trade_id)), None)
        if not record: return
        legs = json.loads(record["legs_json"] or "[]")
        leg_text = "\n".join(f"• {x['action']} {x.get('quantity', 0)} {x['option_type']} {float(x['strike']):,.0f} @ ₹{float(x['price']):,.2f}" for x in legs)
        cashflow = float(record["entry_cashflow"] or 0)
        premium_text = (
            f"Net premium received ₹{cashflow:,.2f}"
            if cashflow > 0 else f"Net premium payable ₹{abs(cashflow):,.2f}"
        )
        has_short = any(str(x.get("action")).upper() == "SELL" for x in legs)
        broker_text = (
            "Broker blocked margin: NOT FETCHED — basket/SPAN calculator quote required"
            if has_short else "Account cash before charges: net premium payable; keep charges/execution buffer"
        )
        self.details.setText(
            f"{record['friendly_name'] or record['strategy_name']} ({record['strategy_name']}) — {record['status']} / {record['outcome']}\n{leg_text}\n"
            f"Saved regime: {record['market_regime'] or 'UNKNOWN'} | {premium_text} | Payoff risk reserve ₹{float(record['capital_required']):,.2f}\n"
            f"{broker_text}\n"
            f"Profit zone: {record['profit_zone']} | Maximum benefit ₹{float(record['max_profit']):,.2f} | Maximum defined loss ₹{float(record['max_loss']):,.2f}\n"
            f"Entry explanation: {record['explanation'] or '-'}\nOutcome review: {record['result_review'] or 'Monitoring; automatic review will be saved at exit.'}\n"
            "Important: payoff maximum loss aur trading-account blocked margin alag figures hain."
        )
