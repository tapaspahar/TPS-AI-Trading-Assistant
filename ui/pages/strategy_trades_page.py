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

        title = QLabel("Strategy Trades — Defined-Risk Paper Validation")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Cutie live option-chain se multiple fully-hedged structures compare karke eligible candidates ko "
            "automatic paper ledger mein capture karti hai. Maximum benefit/loss expiry-payoff model hai; profit "
            "guaranteed nahi hai aur koi broker order place nahi hota. Uncovered option selling allowed nahi hai."
        )
        intro.setWordWrap(True); layout.addWidget(intro)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Strategy Trades"); refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh); layout.addLayout(controls)
        self.summary = QLabel("Waiting for Option Strategies analysis..."); self.summary.setWordWrap(True); layout.addWidget(self.summary)

        catalog_title = QLabel("Live strategy comparison / backtest candidates")
        catalog_title.setObjectName("sectionTitle"); layout.addWidget(catalog_title)
        self.catalog = QTableWidget(0, 9)
        self.catalog.setHorizontalHeaderLabels(("Rank", "Strategy", "Bias", "Max/scenario benefit", "Max loss", "Profit zone", "Scenario coverage", "Gate", "Reason"))
        self.catalog.setEditTriggers(QTableWidget.NoEditTriggers); self.catalog.setMinimumHeight(260)
        self.catalog.itemSelectionChanged.connect(self._catalog_detail)
        layout.addWidget(self.catalog)

        ledger_title = QLabel("Captured strategy trades — automatic result history")
        ledger_title.setObjectName("sectionTitle"); layout.addWidget(ledger_title)
        self.ledger = QTableWidget(0, 12)
        self.ledger.setHorizontalHeaderLabels(("Date/time", "Index", "Strategy", "Bias", "Entry spot", "Last spot", "Max benefit", "Max loss", "Model P&L", "Status", "Outcome", "Expiry"))
        self.ledger.setEditTriggers(QTableWidget.NoEditTriggers); self.ledger.setMinimumHeight(310)
        self.ledger.itemSelectionChanged.connect(self._ledger_detail)
        layout.addWidget(self.ledger)
        performance_title = QLabel("Forward-validation leaderboard — actual captured paper outcomes")
        performance_title.setObjectName("sectionTitle"); layout.addWidget(performance_title)
        self.performance = QTableWidget(0, 5)
        self.performance.setHorizontalHeaderLabels(("Strategy", "Closed samples", "Positive outcomes", "Average P&L", "Total P&L"))
        self.performance.setEditTriggers(QTableWidget.NoEditTriggers); self.performance.setMinimumHeight(190)
        layout.addWidget(self.performance)
        self.details = QLabel("Select a strategy to see every leg, payoff zone and outcome explanation.")
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
                remaining = max(0, 20 - used)
                source = dict(result)
                source.update({"symbol": symbol, "spot": spot})
                for candidate in [c for c in self.latest_catalog if c.get("eligible") and c.get("market_aligned")][:remaining]:
                    trade_id = self.db.save_strategy_trade(candidate, source)
                    if trade_id:
                        captured.append(candidate["strategy"])
            for name in captured:
                self.strategy_event.emit({"kind": "CAPTURED", "symbol": symbol, "strategy": name})
            for item in closed:
                self.strategy_event.emit({"kind": "CLOSED", "symbol": symbol, **item})
            self._fill_catalog(); self.refresh()
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            self.summary.setText(f"Strategy paper validation unavailable: {error}")

    def _fill_catalog(self):
        self.catalog.setRowCount(len(self.latest_catalog))
        for row, item in enumerate(self.latest_catalog):
            values = (
                f"{item.get('rank_score', 0):.0f}/100", item["strategy"], item["bias"],
                f"₹{item['max_profit']:,.0f}", f"₹{item['max_loss']:,.0f}", item.get("profit_zone") or "-",
                f"{item.get('scenario_profitable_percent', 0):.0f}% (model scenarios)",
                "PAPER ELIGIBLE" if item.get("eligible") and item.get("market_aligned") else "WATCH",
                item.get("suitability", ""),
            )
            for column, value in enumerate(values): self.catalog.setItem(row, column, QTableWidgetItem(str(value)))
        self.catalog.resizeColumnsToContents(); self.catalog.horizontalHeader().setStretchLastSection(True)

    def refresh(self):
        rows = self.db.get_strategy_trades(limit=1000)
        summary = self.db.get_strategy_trade_summary()
        self.ledger.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (
                f"{item['trade_date']} {str(item['captured_at'])[11:19]}", item["symbol"], item["strategy_name"], item["bias"],
                f"{float(item['entry_spot']):,.2f}", f"{float(item['last_spot']):,.2f}", f"₹{float(item['max_profit']):,.0f}",
                f"₹{float(item['max_loss']):,.0f}", f"₹{float(item['current_pnl']):,.0f}", item["status"], item["outcome"], item["expiry"],
            )
            for column, value in enumerate(values): self.ledger.setItem(row, column, QTableWidgetItem(str(value)))
            self.ledger.item(row, 0).setData(256, int(item["id"]))
        self.ledger.resizeColumnsToContents(); self.ledger.horizontalHeader().setStretchLastSection(True)
        performance = self.db.get_strategy_performance()
        self.performance.setRowCount(len(performance))
        for row, item in enumerate(performance):
            samples = int(item["samples"] or 0); wins = int(item["wins"] or 0)
            values = (item["strategy_name"], samples, f"{wins}/{samples} ({wins * 100 / samples:.1f}%)" if samples else "0/0",
                      f"₹{float(item['average_pnl'] or 0):,.2f}", f"₹{float(item['total_pnl'] or 0):,.2f}")
            for column, value in enumerate(values): self.performance.setItem(row, column, QTableWidgetItem(str(value)))
        self.performance.resizeColumnsToContents(); self.performance.horizontalHeader().setStretchLastSection(True)
        total = int(summary.get("total") or 0); closed = int(summary.get("closed_count") or 0); wins = int(summary.get("wins") or 0)
        self.summary.setText(
            f"Paper strategies: {total} | Open: {int(summary.get('open_count') or 0)} | Closed: {closed} | "
            f"Positive model outcomes: {wins}/{closed if closed else 0} | Realized model P&L: ₹{float(summary.get('pnl') or 0):,.2f}. "
            "Release 1.4.6 testing cap: 20 unique strategy captures/day."
        )

    def _catalog_detail(self):
        row = self.catalog.currentRow()
        if row < 0 or row >= len(self.latest_catalog): return
        item = self.latest_catalog[row]
        legs = "\n".join(f"• {x['action']} {x['quantity']} {x['option_type']} {x['strike']:,.0f} @ ₹{x['price']:,.2f}" for x in item["legs"])
        self.details.setText(
            f"{item['strategy']} | {item['family']} | Rank {item['rank_score']:.0f}/100\n{legs}\n"
            f"Breakeven(s): {', '.join(f'{x:,.2f}' for x in item.get('breakevens', [])) or '-'} | Profit zone: {item.get('profit_zone')}\n"
            f"{item.get('explanation')}\nSuitability: {item.get('suitability')}"
        )

    def _ledger_detail(self):
        row = self.ledger.currentRow()
        if row < 0 or not self.ledger.item(row, 0): return
        trade_id = self.ledger.item(row, 0).data(256)
        record = next((x for x in self.db.get_strategy_trades(limit=5000) if int(x["id"]) == int(trade_id)), None)
        if not record: return
        legs = json.loads(record["legs_json"] or "[]")
        leg_text = "\n".join(f"• {x['action']} {x.get('quantity', 0)} {x['option_type']} {float(x['strike']):,.0f} @ ₹{float(x['price']):,.2f}" for x in legs)
        self.details.setText(
            f"{record['strategy_name']} — {record['status']} / {record['outcome']}\n{leg_text}\n"
            f"Profit zone: {record['profit_zone']} | Maximum benefit ₹{float(record['max_profit']):,.2f} | Maximum defined loss ₹{float(record['max_loss']):,.2f}\n"
            f"Entry explanation: {record['explanation'] or '-'}\nOutcome review: {record['result_review'] or 'Monitoring; automatic review will be saved at exit.'}"
        )
