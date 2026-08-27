from __future__ import annotations

import json
from datetime import datetime, time
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHeaderView, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.auto_universe_store import AutoUniverseStore
from services.auto_opportunity_service import AutoOpportunityService
from services.live_session import LiveSession
from services.notification_service import NotificationService
from ui.widgets.cards.dashboard_card import DashboardCard
from ui.widgets.excel_export_dialog import open_excel_export


class AutoOpportunityPage(QWidget):
    results_ready = Signal(list)
    scan_failed = Signal(str)
    progress_ready = Signal(int, int, str)
    execution_requested = Signal(dict)

    def __init__(self):
        super().__init__()
        self.scanning = False
        self.db = Database()
        self.last_bucket = None
        self.last_notified = set()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(14, 12, 14, 18); layout.setSpacing(9)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("TPS Auto Opportunity Radar"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Fully automatic read-only research: TPS first discovers the most active and liquid stocks from the complete NSE F&O universe, then after each completed 5-minute candle deeply scans those stocks, their options and all three index options. Manual watchlists remain optional. It publishes entry, protective exit, two targets, R:R and exact evidence only when the underlying TPS engine qualifies the setup. No broker order is placed."
        )
        note.setWordWrap(True); layout.addWidget(note)
        self.status = QLabel("AUTO MODE ON — waiting for broker connection and the next completed 5-minute candle.")
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.run = QPushButton("Run Diagnostic Scan Now")
        self.run.clicked.connect(lambda: self.scan(force=True)); layout.addWidget(self.run)
        excel = QPushButton("Export Opportunity Report to Excel by Date / Period")
        excel.clicked.connect(lambda: open_excel_export(self, self.db, "opportunities")); layout.addWidget(excel)

        grid = QGridLayout(); self.cards = {
            "last": DashboardCard("Last automatic scan", "Waiting"),
            "scope": DashboardCard("Automatic scope", "3 indices\nFull F&O discovery"),
            "actionable": DashboardCard("Current candidates", "0"),
            "mode": DashboardCard("Execution mode", "RESEARCH / PAPER\nNo broker order"),
        }
        for column, card in enumerate(self.cards.values()):
            card.set_compact(True); card.setMinimumHeight(92); grid.addWidget(card, 0, column)
        layout.addLayout(grid)
        self.auto_selection = QLabel("Auto-selected F&O stocks: waiting for the first live universe scan.")
        self.auto_selection.setWordWrap(True); layout.addWidget(self.auto_selection)
        table_box = QGroupBox("Latest automatic market opportunities")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels((
            "Candle", "Market", "Symbol", "Action", "Instrument", "Score", "Entry", "Stop / Exit",
            "Target 1", "Target 2", "Qty", "R:R", "State", "Reason",
        ))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(360); self.table.itemSelectionChanged.connect(self.show_selected)
        table_layout.addWidget(self.table); layout.addWidget(table_box)
        detail_box = QGroupBox("Selected suggestion — evidence and exit conditions")
        detail_layout = QVBoxLayout(detail_box); self.detail = QLabel("Select a row to inspect every reason.")
        self.detail.setWordWrap(True); detail_layout.addWidget(self.detail); layout.addWidget(detail_box)
        self.prepare_execution = QPushButton("Prepare Selected Suggestion in Broker Execution")
        self.prepare_execution.clicked.connect(self._prepare_selected_execution)
        self.prepare_execution.setEnabled(False)
        detail_layout.addWidget(self.prepare_execution)
        layout.addStretch()

        self.results_ready.connect(self.show_results); self.scan_failed.connect(self.show_error)
        self.progress_ready.connect(self.show_progress)
        self.timer = QTimer(self); self.timer.setInterval(15_000); self.timer.timeout.connect(self._automatic_tick); self.timer.start()
        self.refresh_history()
        QTimer.singleShot(2500, self._automatic_tick)

    def _automatic_tick(self):
        now = datetime.now()
        if now.weekday() >= 5 or not (time(9, 20) <= now.time() <= time(15, 25)):
            return
        bucket = now.strftime("%Y-%m-%d-%H-") + f"{(now.minute // 5) * 5:02d}"
        if now.minute % 5 == 0 and now.second >= 8 and bucket != self.last_bucket:
            self.last_bucket = bucket
            self.scan()

    def scan(self, force=False):
        if self.scanning:
            return
        if not LiveSession.connected():
            self.status.setText("Cutie keh rahi hai: broker live data disconnected hai; main automatically retry karungi.")
            return
        now = datetime.now()
        if not force and (now.weekday() >= 5 or not (time(9, 20) <= now.time() <= time(15, 25))):
            return
        self.scanning = True; self.run.setEnabled(False)
        self.status.setText("Automatic completed-candle scan started. Broker API limits ke liye symbols sequentially check ho rahe hain...")
        Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            service = AutoOpportunityService(LiveSession.client)
            self.results_ready.emit(service.scan(lambda done, total, label: self.progress_ready.emit(done, total, label)))
        except Exception as error:  # UI boundary: report the failure and let the next timed cycle retry.
            self.scan_failed.emit(str(error))

    def show_progress(self, done, total, label):
        self.status.setText(f"Automatic scan {done}/{total}: {label} completed.")

    def show_results(self, results):
        database = Database(); database.save_auto_opportunities(results); database.close()
        actionable = [row for row in results if row.get("action") not in ("WAIT", "ERROR")]
        self.cards["last"].set_value(datetime.now().strftime("%d-%m-%Y\n%H:%M:%S"))
        self.cards["actionable"].set_value(str(len(actionable)))
        selected = AutoUniverseStore().load()
        if selected:
            labels = [f"{row['underlying']} ({float(row.get('selection_score') or 0):.0f})" for row in selected]
            self.auto_selection.setText("Auto-selected F&O stocks for deep scan: " + " | ".join(labels))
        self.status.setText(
            f"AUTO MODE ON — {len(results)} instruments evaluated | {len(actionable)} research candidate(s). Next scan after next completed 5-minute candle."
        )
        self.scanning = False; self.run.setEnabled(True); self.refresh_history()
        notifier = NotificationService.instance(self)
        for row in actionable:
            identity = (row.get("candle_time"), row.get("market_type"), row.get("symbol"), row.get("action"))
            if identity in self.last_notified:
                continue
            self.last_notified.add(identity)
            notifier.notify(
                "auto_opportunity", f"TPS Opportunity: {row['action']} {row['symbol']}",
                f"{row.get('instrument')} | Entry {row.get('entry')} | Stop {row.get('stop')} | T1 {row.get('target_1')} | Score {row.get('score')}/100",
                dedupe_key=f"{row.get('symbol')}:{row.get('action')}:{row.get('instrument')}",
                once_per_day=True,
            )

    def refresh_history(self):
        database = Database(); rows = database.get_auto_opportunities(250); database.close()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            details = json.loads(row["details_json"] or "{}")
            reason = "; ".join((details.get("blockers") or details.get("evidence") or [row["exit_rule"]])[:2])
            values = (
                row["candle_time"], row["market_type"], row["symbol"], row["action"], row["instrument"] or "-",
                f"{row['score']:.0f}/100", self._price(row["entry"]), self._price(row["stop"]),
                self._price(row["target_1"]), self._price(row["target_2"]), row["quantity"] or "-",
                f"{row['rr_ratio']:.2f}" if row["rr_ratio"] is not None else "-", row["state"], reason,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setData(256, dict(row)); self.table.setItem(index, column, item)
        self.table.horizontalHeader().setStretchLastSection(True)
        from core.settings_store import SettingsStore
        mode = str(SettingsStore().load().get("execution_mode", "PAPER")).upper()
        self.cards["mode"].set_value(f"{mode} REVIEW\nSafeguards required")

    def show_selected(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return
        record = self.table.item(row, 0).data(256); details = json.loads(record.get("details_json") or "{}")
        self.prepare_execution.setEnabled(str(record.get("action") or "").upper() not in ("WAIT", "ERROR", ""))
        evidence = "\n• ".join(details.get("evidence") or ["No confirming evidence published."])
        blockers = "\n• ".join(details.get("blockers") or ["None — research candidate gates passed."])
        self.detail.setText(
            f"{record['action']} {record['symbol']} | {record.get('instrument') or '-'} | Score {record['score']:.0f}/100\n"
            f"Entry price: ₹{self._price(record.get('entry'))} | Protective stop: ₹{self._price(record.get('stop'))}\n"
            f"First target: ₹{self._price(record.get('target_1'))} | Second target: ₹{self._price(record.get('target_2'))}\n"
            f"Exit logic: {record['exit_rule']}\n\nEvidence:\n• {evidence}\n\nBlockers / caution:\n• {blockers}\n\n"
            "Suggestion completed-candle research hai; live spread/slippage aur unexpected news ko manually verify karna zaroori hai."
        )

    def _prepare_selected_execution(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return
        record = dict(self.table.item(row, 0).data(256) or {})
        action = str(record.get("action") or "").upper()
        if action in ("WAIT", "ERROR", ""):
            return
        self.execution_requested.emit({"kind": "OPPORTUNITY", "record": record})

    def show_error(self, message):
        self.scanning = False; self.run.setEnabled(True)
        self.status.setText(f"AUTO MODE ON — scan error: {message}. TPS next 5-minute cycle par automatically retry karega.")

    @staticmethod
    def _price(value):
        return f"{float(value):,.2f}" if value is not None else "-"
