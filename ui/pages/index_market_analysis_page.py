"""Live and post-close three-index explanation workspace."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.database_manager import Database
from core.market_session import market_session
from services.index_market_analysis_service import IndexMarketAnalysisService
from services.analysis_scheduler import AnalysisScheduler
from services.live_session import LiveSession


class IndexMarketAnalysisPage(QWidget):
    scan_ready = Signal(dict)
    scan_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.scanning = False
        self.last_auto_bucket = None
        self.last_finalized_day = None
        self._render_signature = None
        layout = QVBoxLayout(self)
        title = QLabel("Live Index Intelligence & After Market Analysis")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel("NIFTY, BANKNIFTY aur SENSEX ki har completed 5-minute future candle ko price, volume aur near-ATM OI/COI ke saath automatically explain karta hai. Market close ke baad isi evidence se saved conclusion banta hai.")
        intro.setWordWrap(True); layout.addWidget(intro)
        controls = QHBoxLayout(); controls.addWidget(QLabel("Trading date"))
        self.date = QDateEdit(QDate.currentDate()); self.date.setCalendarPopup(True); self.date.setDisplayFormat("dd-MM-yyyy"); controls.addWidget(self.date)
        refresh = QPushButton("Refresh Saved Analysis"); refresh.clicked.connect(self.refresh); controls.addWidget(refresh)
        self.scan_button = QPushButton("Analyze Latest Completed Candle Now"); self.scan_button.clicked.connect(lambda: self.scan(force=True)); controls.addWidget(self.scan_button)
        layout.addLayout(controls)
        self.status = QLabel("Broker connect hote hi automatic 5-minute monitor start hoga."); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.cross_index = QLabel(); self.cross_index.setObjectName("sectionTitle"); self.cross_index.setWordWrap(True); layout.addWidget(self.cross_index)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(("Candle", "Index", "Direction", "Move", "Future volume", "Aggression", "OI flow", "Call COI", "Put COI", "Evidence explanation"))
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(72)
        for column in range(9):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.Interactive)
        self.table.setColumnWidth(9, 640)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 2)
        layout.addWidget(QLabel("After Market Analysis of Index — saved conclusion"))
        self.report = QPlainTextEdit(); self.report.setReadOnly(True); layout.addWidget(self.report, 1)
        self.scan_ready.connect(self._scan_finished); self.scan_failed.connect(self._scan_failed)
        self.timer = QTimer(self); self.timer.setInterval(30_000); self.timer.timeout.connect(self.scan)
        self.refresh()

    def start_monitoring(self):
        self.timer.start(); self.scan(force=True)

    def scan(self, _checked=False, force=False):
        if self.scanning or LiveSession.client is None:
            if force and LiveSession.client is None: self.status.setText("Live broker data connected nahi hai; saved report available hai.")
            return
        now = datetime.now()
        session = market_session(now)
        if session["state"] in {"WEEKEND", "HOLIDAY", "BEFORE_OPEN", "PRE_OPEN"}:
            self.status.setText(f"Automatic analysis paused — {session['label']}. Saved history available hai.")
            return
        if session["state"] == "CLOSED":
            day = now.date().isoformat()
            if day == self.last_finalized_day:
                self.status.setText("Market closed — final index conclusion saved; live scanning paused.")
                return
            # Exactly one closing refresh is allowed so the final completed
            # candle reaches the daily report. Further 30-second/5-minute
            # polling remains stopped until the next live session.
            self.last_finalized_day = day
        bucket = (now.date(), now.hour, now.minute // 5)
        if not force and (now.minute % 5 != 0 or now.second > 35 or bucket == self.last_auto_bucket): return
        self.scanning = True; self.scan_button.setEnabled(False); self.status.setText("Teenon indices ki latest completed candle background me analyze ho rahi hai…")
        self._pending_bucket = bucket
        if not AnalysisScheduler.submit_unique("index-market-analysis", lambda: self._scan_worker(now)):
            self.scanning = False; self.scan_button.setEnabled(True)

    def _scan_worker(self, now):
        database = Database()
        try:
            self.scan_ready.emit(IndexMarketAnalysisService(LiveSession.client, database).scan_all(now))
        except Exception as error:
            self.scan_failed.emit(str(error))
        finally:
            database.close()

    def _scan_finished(self, result):
        self.last_auto_bucket = self._pending_bucket
        self.scanning = False; self.scan_button.setEnabled(True)
        self.status.setText(f"Auto monitor active | {len(result['results'])}/3 indices refreshed" + (f" | Data gaps: {'; '.join(result['errors'])}" if result["errors"] else ""))
        self.refresh()

    def _scan_failed(self, message):
        self.scanning = False; self.scan_button.setEnabled(True)
        self.status.setText(f"Analysis DATA GAP: {message}")

    def refresh(self, _checked=False):
        day = self.date.date().toString("dd-MM-yyyy")
        rows = self.db.get_index_candle_analyses(day); self.table.setRowCount(len(rows))
        signature = (day, len(rows), str(rows[0]["candle_time"]) if rows else "")
        if signature == self._render_signature:
            return
        self._render_signature = signature
        self.table.setUpdatesEnabled(False)
        for i, row in enumerate(rows):
            values = (str(row["candle_time"])[11:16], row["symbol"], row["direction"], f"{float(row['move_points'] or 0):+,.2f} pts",
                      f"{float(row['volume_ratio']):.2f}x" if row["volume_ratio"] is not None else "DATA GAP", row["aggression"],
                      f"{row['oi_direction']} ({int(row['oi_quality'] or 0)}/100)", f"{float(row['call_coi'] or 0):+,.0f}", f"{float(row['put_coi'] or 0):+,.0f}", row["explanation"])
            for j, value in enumerate(values): self.table.setItem(i, j, QTableWidgetItem(str(value)))
        # Resize the compact evidence columns from their current contents;
        # the explanation column intentionally keeps a readable fixed width
        # and uses the horizontal scrollbar on smaller screens.
        if rows:
            self.table.resizeColumnsToContents()
            self.table.setColumnWidth(9, min(max(640, self.table.columnWidth(9)), 900))
            self.table.resizeRowsToContents()
        latest = {s: next((r for r in rows if r["symbol"] == s), None) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
        present = [f"{s} {r['direction']}" for s, r in latest.items() if r]
        self.cross_index.setText("Cross-index latest: " + (" | ".join(present) if present else "saved candle data unavailable"))
        report = self.db.get_index_daily_analysis(day)
        self.report.setPlainText(str(report["summary_text"]) if report else "Is date ka conclusion abhi available nahi hai.")
        self.table.setUpdatesEnabled(True)
