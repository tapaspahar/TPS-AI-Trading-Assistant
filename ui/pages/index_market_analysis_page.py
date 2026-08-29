"""Live and post-close three-index explanation workspace."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.database_manager import Database
from services.index_market_analysis_service import IndexMarketAnalysisService
from services.live_session import LiveSession


class IndexMarketAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.scanning = False
        self.last_auto_bucket = None
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
        self.table.setWordWrap(True); self.table.setAlternatingRowColors(True); self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 2)
        layout.addWidget(QLabel("After Market Analysis of Index — saved conclusion"))
        self.report = QPlainTextEdit(); self.report.setReadOnly(True); layout.addWidget(self.report, 1)
        self.timer = QTimer(self); self.timer.setInterval(30_000); self.timer.timeout.connect(self.scan)
        self.refresh()

    def start_monitoring(self):
        self.timer.start(); self.scan(force=True)

    def scan(self, _checked=False, force=False):
        if self.scanning or LiveSession.client is None:
            if force and LiveSession.client is None: self.status.setText("Live broker data connected nahi hai; saved report available hai.")
            return
        now = datetime.now()
        bucket = (now.date(), now.hour, now.minute // 5)
        if not force and (now.minute % 5 != 0 or now.second > 35 or bucket == self.last_auto_bucket): return
        self.scanning = True; self.scan_button.setEnabled(False); self.status.setText("Teenon indices ki latest completed candle analyze ho rahi hai…")
        try:
            result = IndexMarketAnalysisService(LiveSession.client, self.db).scan_all(now)
            self.last_auto_bucket = bucket
            self.status.setText(f"Auto monitor active | {len(result['results'])}/3 indices refreshed" + (f" | Data gaps: {'; '.join(result['errors'])}" if result["errors"] else ""))
            self.refresh()
        except (RuntimeError, ValueError) as error:
            self.status.setText(f"Analysis DATA GAP: {error}")
        finally:
            self.scanning = False; self.scan_button.setEnabled(True)

    def refresh(self, _checked=False):
        day = self.date.date().toString("dd-MM-yyyy")
        rows = self.db.get_index_candle_analyses(day); self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = (str(row["candle_time"])[11:16], row["symbol"], row["direction"], f"{float(row['move_points'] or 0):+,.2f} pts",
                      f"{float(row['volume_ratio']):.2f}x" if row["volume_ratio"] is not None else "DATA GAP", row["aggression"],
                      f"{row['oi_direction']} ({int(row['oi_quality'] or 0)}/100)", f"{float(row['call_coi'] or 0):+,.0f}", f"{float(row['put_coi'] or 0):+,.0f}", row["explanation"])
            for j, value in enumerate(values): self.table.setItem(i, j, QTableWidgetItem(str(value)))
        latest = {s: next((r for r in rows if r["symbol"] == s), None) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
        present = [f"{s} {r['direction']}" for s, r in latest.items() if r]
        self.cross_index.setText("Cross-index latest: " + (" | ".join(present) if present else "saved candle data unavailable"))
        report = self.db.get_index_daily_analysis(day)
        self.report.setPlainText(str(report["summary_text"]) if report else "Is date ka conclusion abhi available nahi hai.")
