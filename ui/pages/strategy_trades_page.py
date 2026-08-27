import json
from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.market_session import IST, market_session, parse_session_times
from core.settings_store import SettingsStore
from engine.strategy_portfolio_engine import build_strategy_catalog
from ui.widgets.excel_export_dialog import open_excel_export


def capturable_strategy_candidates(catalog, remaining):
    """Return bounded-risk candidates for paper validation, best-ranked first.

    Market-aligned rows are the primary study; eligible opposite-regime rows are
    retained as counterfactual evidence so the validation page does not go blank.
    """
    return [
        candidate for candidate in catalog
        if candidate.get("eligible")
    ][:max(0, int(remaining or 0))]


def candidate_structure_key(candidate):
    return "|".join(
        f"{leg['action']}:{leg['option_type']}:{float(leg['strike']):g}:{int(leg.get('lots', 1))}"
        for leg in candidate.get("legs", [])
    )


def strategy_capture_window(now=None, settings=None, observation_minutes=15):
    """Return the automatic strategy-study stage for the configured session."""
    now = now.astimezone(IST) if now and now.tzinfo else now.replace(tzinfo=IST) if now else datetime.now(IST)
    session = market_session(now, settings)
    if session.get("state") != "OPEN":
        return session.get("state", "CLOSED"), None
    _, open_clock, _ = parse_session_times(settings)
    ready_at = datetime.combine(now.date(), open_clock, IST) + timedelta(minutes=observation_minutes)
    return ("OBSERVING", ready_at) if now < ready_at else ("CHECKING", ready_at)


class StrategyTradesPage(QWidget):
    """Automatic, multi-leg defined-risk paper validation ledger."""

    strategy_event = Signal(dict)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings = SettingsStore()
        self.latest_catalog = []
        self.latest_result = {}
        self._finalized_session_key = ""
        self.session_message = ""
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
        export = QPushButton("Export Individual Reports to Excel")
        export.clicked.connect(lambda: open_excel_export(self, self.db, "strategy_trades"))
        controls.addWidget(refresh); controls.addWidget(export); layout.addLayout(controls)
        self.summary = QLabel("Waiting for Option Strategies analysis..."); self.summary.setWordWrap(True); layout.addWidget(self.summary)

        live_title = QLabel("Live analysed strategies — current market comparison (maximum 30)")
        live_title.setObjectName("sectionTitle"); layout.addWidget(live_title)
        self.live_catalog = QTableWidget(0, 11)
        self.live_catalog.setHorizontalHeaderLabels((
            "Rank", "Cutie name / structure", "Market fit", "Model score",
            "Scenario-positive coverage", "Payoff ratio", "Risk reserve",
            "Maximum benefit", "Maximum loss", "Bias", "Suitability",
        ))
        self.live_catalog.setEditTriggers(QTableWidget.NoEditTriggers)
        self.live_catalog.setMinimumHeight(270)
        layout.addWidget(self.live_catalog)
        live_note = QLabel(
            "Scenario-positive coverage model ke tested expiry-price points ka percentage hai; "
            "ye actual win rate ya guaranteed profit nahi hai. Actual win rate sirf closed paper outcomes se banta hai."
        )
        live_note.setWordWrap(True); layout.addWidget(live_note)

        performance_title = QLabel("Strategy ranking — actual closed paper win rate (top rank first)")
        performance_title.setObjectName("sectionTitle"); layout.addWidget(performance_title)
        self.performance = QTableWidget(0, 12)
        self.performance.setHorizontalHeaderLabels(("Rank", "Cutie name / structure", "Validation", "Closed trades", "Wins", "Win rate", "95% lower bound", "Expectancy", "Profit factor", "Total P&L", "Avg capture ROC", "Observed regimes"))
        self.performance.setEditTriggers(QTableWidget.NoEditTriggers); self.performance.setMinimumHeight(220)
        layout.addWidget(self.performance)

        closed_title = QLabel("Individual closed strategy reports — every closed trade is one separate report")
        closed_title.setObjectName("sectionTitle"); layout.addWidget(closed_title)
        closed_note = QLabel(
            "Example: ranking me Closed trades 10 ka matlab neeche us strategy ki 10 alag reports hain. "
            "Har row ka apna entry, exit, P&L, result aur review hai."
        )
        closed_note.setWordWrap(True); layout.addWidget(closed_note)
        self.closed_reports = QTableWidget(0, 14)
        self.closed_reports.setHorizontalHeaderLabels((
            "Report ID", "Trading date", "Close time", "Index", "Cutie name", "Structure",
            "Entry spot", "Exit spot", "Realized P&L", "Result", "Regime", "Bias",
            "Capture score", "Expiry",
        ))
        self.closed_reports.setEditTriggers(QTableWidget.NoEditTriggers)
        self.closed_reports.setMinimumHeight(300)
        self.closed_reports.itemSelectionChanged.connect(self._closed_report_detail)
        layout.addWidget(self.closed_reports)
        self.closed_details = QLabel("Kisi closed report ko select karke complete legs aur outcome review dekhiye.")
        self.closed_details.setWordWrap(True); self.closed_details.setMinimumHeight(120)
        layout.addWidget(self.closed_details)

        ledger_title = QLabel("Captured strategy trades — automatic result history")
        ledger_title.setObjectName("sectionTitle"); layout.addWidget(ledger_title)
        self.ledger = QTableWidget(0, 17)
        self.ledger.setHorizontalHeaderLabels(("Date/time", "Index", "Cutie name", "Structure", "Capture score", "Scenario score", "Regime", "Bias", "Entry spot", "Last spot", "Payoff risk reserve", "Max benefit", "Max loss", "Model P&L", "Status", "Outcome", "Expiry"))
        self.ledger.setEditTriggers(QTableWidget.NoEditTriggers); self.ledger.setMinimumHeight(310)
        self.ledger.itemSelectionChanged.connect(self._ledger_detail)
        layout.addWidget(self.ledger)
        self.details = QLabel("Captured trade select karke every leg, saved score, payoff zone aur outcome explanation dekhiye.")
        self.details.setWordWrap(True); self.details.setMinimumHeight(110); layout.addWidget(self.details)
        review_title = QLabel("Market-close strategy analysis — date-wise permanent learning record")
        review_title.setObjectName("sectionTitle"); layout.addWidget(review_title)
        self.reviews = QTableWidget(0, 9)
        self.reviews.setHorizontalHeaderLabels(("Date", "Index", "Direction", "Regime", "Checked", "Profitable", "Loss", "Best strategy", "Best P&L"))
        self.reviews.setEditTriggers(QTableWidget.NoEditTriggers); self.reviews.setMinimumHeight(190)
        self.reviews.itemSelectionChanged.connect(self._review_detail); layout.addWidget(self.reviews)
        self.review_details = QLabel("Market close ke baad Cutie ka automatic comparison yahan save hoga.")
        self.review_details.setWordWrap(True); self.review_details.setMinimumHeight(70); layout.addWidget(self.review_details)
        layout.addStretch(); self.refresh()
        self.session_timer = QTimer(self); self.session_timer.setInterval(30_000)
        self.session_timer.timeout.connect(self._session_tick); self.session_timer.start()

    def ingest_analysis(self, result: dict):
        """Receive the same completed-candle evidence used by Option Strategies."""
        try:
            self.latest_result = dict(result)
            self.latest_catalog = build_strategy_catalog(result, self.settings.load())
            symbol = str(result.get("symbol") or "").upper()
            spot = float(result.get("spot") or 0)
            quote_rows = (result.get("chain") or {}).get("quote_rows") or []
            closed = self.db.update_strategy_trades(symbol, spot, str(result.get("candle_time") or ""), quote_rows) if symbol and spot else []
            loaded_settings = self.settings.load()
            today = datetime.now(IST).strftime("%d-%m-%Y")
            session = market_session(settings=loaded_settings)
            stage, ready_at = strategy_capture_window(settings=loaded_settings)
            captured = []
            if stage == "CHECKING":
                saved_today = self.db.get_strategy_trades(today, 100)
                used = len(saved_today)
                remaining = max(0, 30 - used)
                existing_keys = {str(row["structure_key"]) for row in saved_today}
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
                for candidate in capturable_strategy_candidates(self.latest_catalog, len(self.latest_catalog)):
                    if len(captured) >= remaining:
                        break
                    if candidate_structure_key(candidate) in existing_keys:
                        continue
                    candidate_source = dict(source)
                    aligned = bool(candidate.get("market_alignment"))
                    candidate_source.update({
                        "strategy_market_alignment": aligned,
                        "strategy_validation_track": "PRIMARY" if aligned else "COUNTERFACTUAL",
                        "strategy_target_profit_amount": float(loaded_settings.get("strategy_daily_target_profit") or 0),
                        "strategy_stop_loss_amount": float(loaded_settings.get("strategy_daily_max_loss") or 0),
                    })
                    trade_id = self.db.save_strategy_trade(candidate, candidate_source)
                    if trade_id:
                        captured.append(candidate.get("friendly_name") or candidate["strategy"])
                        existing_keys.add(candidate_structure_key(candidate))
                self.session_message = (
                    f"Checking mode active — first 15-minute observation complete. "
                    f"Aaj ke {used + len(captured)}/30 unique strategy combinations paper monitor par hain."
                )
            elif stage == "OBSERVING":
                self.session_message = f"Cutie first 15-minute market structure observe kar rahi hai. Strategy checking {ready_at.strftime('%H:%M')} IST se start hogi."
            elif session.get("state") == "CLOSED":
                self._finalize_session(result)
            for name in captured:
                self.strategy_event.emit({"kind": "CAPTURED", "symbol": symbol, "strategy": name})
            for item in closed:
                self.strategy_event.emit({"kind": "CLOSED", "symbol": symbol, **item})
            self.refresh()
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            self.summary.setText(f"Strategy paper validation unavailable: {error}")

    def _session_tick(self):
        if self.latest_result and market_session(settings=self.settings.load()).get("state") == "CLOSED":
            self._finalize_session(self.latest_result)
            today = datetime.now(IST).strftime("%d-%m-%Y")
            reconciled = self.db.finalize_open_strategy_sessions(today)
            if reconciled:
                closed_count = sum(len(item.get("closed") or []) for item in reconciled)
                symbols = ", ".join(item["symbol"] for item in reconciled)
                self.session_message = (
                    f"Market-close reconciliation complete — {closed_count} remaining simulations closed; "
                    f"date-wise reviews refreshed for {symbols}."
                )
                self.refresh()

    def _finalize_session(self, result):
        symbol = str(result.get("symbol") or "").upper()
        spot = float(result.get("spot") or 0)
        if not symbol or not spot:
            return
        today = datetime.now(IST).strftime("%d-%m-%Y")
        key = f"{today}:{symbol}"
        if key == self._finalized_session_key:
            return
        quote_rows = (result.get("chain") or {}).get("quote_rows") or []
        closed = self.db.update_strategy_trades(symbol, spot, str(result.get("candle_time") or ""), quote_rows, force_close=True)
        regime = str(result.get("market_regime") or (result.get("environment") or {}).get("regime") or "UNKNOWN").upper()
        direction = str(result.get("bias") or result.get("market_bias") or "UNKNOWN").upper()
        review = self.db.save_strategy_session_review(today, symbol, direction, regime)
        if review and key != self._finalized_session_key:
            self._finalized_session_key = key
            self.session_message = f"Market-close review saved — {review.get('wins', 0)}/{review.get('total_strategies', 0)} strategies profitable."
            self.strategy_event.emit({"kind": "SESSION_REVIEW", "symbol": symbol, "strategy": review.get("best_strategy") or "-"})
        for item in closed:
            self.strategy_event.emit({"kind": "CLOSED", "symbol": symbol, **item})
        self.refresh()

    def refresh(self):
        self.live_catalog.setRowCount(len(self.latest_catalog))
        for row, item in enumerate(self.latest_catalog):
            aligned = bool(item.get("market_alignment"))
            eligible = bool(item.get("eligible"))
            values = (
                row + 1,
                f"{item.get('friendly_name') or item.get('strategy')} / {item.get('strategy')}",
                "PRIMARY MATCH" if aligned else "COUNTERFACTUAL",
                f"{float(item.get('rank_score') or 0):.0f}/100",
                f"{float(item.get('scenario_profitable_percent') or 0):.1f}%",
                f"{float(item.get('payoff_ratio') or 0):.2f}",
                f"₹{float(item.get('capital_required') or 0):,.0f}",
                f"₹{float(item.get('max_profit') or 0):,.0f}",
                f"₹{float(item.get('max_loss') or 0):,.0f}",
                item.get("bias") or "UNKNOWN",
                ("PAPER ELIGIBLE — " if eligible else "COMPARISON ONLY — ") + str(item.get("suitability") or ""),
            )
            for column, value in enumerate(values):
                self.live_catalog.setItem(row, column, QTableWidgetItem(str(value)))
        self.live_catalog.resizeColumnsToContents()
        self.live_catalog.horizontalHeader().setStretchLastSection(True)

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
            values = (row + 1, f"{item['friendly_name']} / {item['strategy_name']}", item["validation_tier"], samples, wins,
                      f"{float(item['win_rate'] or 0):.1f}%", f"{float(item['wilson_lower_bound'] or 0):.1f}%",
                      f"₹{float(item['average_pnl'] or 0):,.2f}", f"{float(item['profit_factor'] or 0):.2f}",
                      f"₹{float(item['total_pnl'] or 0):,.2f}", f"{float(item['average_model_roc'] or 0):.1f}%", item["market_regimes"] or "UNKNOWN")
            for column, value in enumerate(values): self.performance.setItem(row, column, QTableWidgetItem(str(value)))
        self.performance.resizeColumnsToContents(); self.performance.horizontalHeader().setStretchLastSection(True)
        closed_rows = [item for item in rows if str(item["status"]).upper() == "CLOSED"]
        self.closed_reports.setRowCount(len(closed_rows))
        for row, item in enumerate(closed_rows):
            values = (
                f"STR-{int(item['id']):05d}", item["trade_date"], str(item["exit_at"] or "")[11:19] or "-",
                item["symbol"], item["friendly_name"] or item["strategy_name"], item["strategy_name"],
                f"{float(item['entry_spot'] or 0):,.2f}", f"{float(item['last_spot'] or 0):,.2f}",
                f"₹{float(item['realized_pnl'] or 0):,.2f}", item["outcome"],
                item["market_regime"] or "UNKNOWN", item["bias"] or "UNKNOWN",
                f"{float(item['rank_score'] or 0):.0f}/100", item["expiry"],
            )
            for column, value in enumerate(values):
                self.closed_reports.setItem(row, column, QTableWidgetItem(str(value)))
            self.closed_reports.item(row, 0).setData(256, int(item["id"]))
        self.closed_reports.resizeColumnsToContents()
        self.closed_reports.horizontalHeader().setStretchLastSection(True)
        reviews = self.db.get_strategy_session_reviews()
        self.reviews.setRowCount(len(reviews))
        for row, item in enumerate(reviews):
            values = (item["trade_date"], item["symbol"], item["market_direction"], item["market_regime"],
                      item["total_strategies"], item["wins"], item["losses"], item["best_strategy"], f"₹{float(item['best_pnl']):,.2f}")
            for column, value in enumerate(values): self.reviews.setItem(row, column, QTableWidgetItem(str(value)))
            self.reviews.item(row, 0).setData(256, int(item["id"]))
        self.reviews.resizeColumnsToContents(); self.reviews.horizontalHeader().setStretchLastSection(True)
        total = int(summary.get("total") or 0); closed = int(summary.get("closed_count") or 0); wins = int(summary.get("wins") or 0)
        today = datetime.now(IST).strftime("%d-%m-%Y")
        daily = self.db.get_strategy_daily_pnl(today)
        guard_settings = SettingsStore().load()
        target = float(guard_settings.get("strategy_daily_target_profit") or 0)
        max_loss = float(guard_settings.get("strategy_daily_max_loss") or 0)
        measured_rate = (100.0 * wins / closed) if closed else 0.0
        validated = sum(item.get("validation_tier") == "VALIDATED LOW-RISK" for item in performance)
        self.summary.setText(
            (self.session_message + "\n" if self.session_message else "") +
            f"Live analysed: {len(self.latest_catalog)}/30 | "
            f"Paper strategies: {total} | Open: {int(summary.get('open_count') or 0)} | Closed: {closed} | "
            f"Measured wins: {wins}/{closed if closed else 0} ({measured_rate:.1f}%) | Net paper P&L: ₹{float(summary.get('pnl') or 0):,.2f} | "
            f"Validated low-risk strategies: {validated}. 70% target requires at least 30 closed outcomes, positive expectancy, profit factor 1.20+ and a conservative confidence check. "
            "Ranking sirf closed paper outcomes ke win rate par hai (tie me zyada samples, phir total P&L). "
            f"Individual closed reports: {len(closed_rows)} | "
            f"Today's combined strategy P&L (report only): ₹{float(daily.get('combined_pnl') or 0):,.2f} | "
            f"Per-strategy target preset: {'₹' + format(target, ',.2f') if target > 0 else 'AUTO'} | "
            f"Per-strategy stop preset: {'₹' + format(max_loss, ',.2f') if max_loss > 0 else 'AUTO'}. "
            "Testing cap: 30 unique multi-strike strategy captures/day."
        )

    def _strategy_detail_text(self, record) -> str:
        legs = json.loads(record["legs_json"] or "[]")
        leg_text = "\n".join(f"• {x['action']} {x.get('quantity', 0)} {x['option_type']} {float(x['strike']):,.0f} @ ₹{float(x['price']):,.2f}" for x in legs)
        cashflow = float(record["entry_cashflow"] or 0)
        premium_text = f"Net premium received ₹{cashflow:,.2f}" if cashflow > 0 else f"Net premium payable ₹{abs(cashflow):,.2f}"
        has_short = any(str(x.get("action")).upper() == "SELL" for x in legs)
        broker_text = "Broker blocked margin: NOT FETCHED — basket/SPAN calculator quote required" if has_short else "Account cash before charges: net premium payable; keep charges/execution buffer"
        return (
            f"Report STR-{int(record['id']):05d} | {record['trade_date']} | {record['friendly_name'] or record['strategy_name']} "
            f"({record['strategy_name']}) — {record['status']} / {record['outcome']}\n{leg_text}\n"
            f"Entry {float(record['entry_spot'] or 0):,.2f} | Exit/last {float(record['last_spot'] or 0):,.2f} | "
            f"Realized P&L ₹{float(record['realized_pnl'] or 0):,.2f}\n"
            f"Saved regime: {record['market_regime'] or 'UNKNOWN'} | {premium_text} | Payoff risk reserve ₹{float(record['capital_required']):,.2f}\n"
            f"{broker_text}\nProfit zone: {record['profit_zone']} | Maximum benefit ₹{float(record['max_profit']):,.2f} | "
            f"Maximum defined loss ₹{float(record['max_loss']):,.2f}\n"
            f"Entry explanation: {record['explanation'] or '-'}\nOutcome review: {record['result_review'] or 'Review pending.'}\n"
            "Important: payoff maximum loss aur trading-account blocked margin alag figures hain."
        )

    def _closed_report_detail(self):
        row = self.closed_reports.currentRow()
        if row < 0 or not self.closed_reports.item(row, 0): return
        trade_id = self.closed_reports.item(row, 0).data(256)
        record = next((x for x in self.db.get_strategy_trades(limit=5000) if int(x["id"]) == int(trade_id)), None)
        if record: self.closed_details.setText(self._strategy_detail_text(record))

    def _review_detail(self):
        row = self.reviews.currentRow()
        if row < 0: return
        review_id = self.reviews.item(row, 0).data(256)
        record = next((x for x in self.db.get_strategy_session_reviews(1000) if int(x["id"]) == int(review_id)), None)
        if record: self.review_details.setText(record["review_text"])

    def _ledger_detail(self):
        row = self.ledger.currentRow()
        if row < 0 or not self.ledger.item(row, 0): return
        trade_id = self.ledger.item(row, 0).data(256)
        record = next((x for x in self.db.get_strategy_trades(limit=5000) if int(x["id"]) == int(trade_id)), None)
        if not record: return
        self.details.setText(self._strategy_detail_text(record))
