"""Live index-component majority/heat-map breadth monitor."""
from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.database_manager import Database
from core.market_session import market_session
from services.analysis_scheduler import AnalysisScheduler
from services.index_component_breadth_service import IndexComponentBreadthService
from engine.index_component_breadth import combine_component_breadth, combine_market_evidence
from services.live_session import LiveSession


class IndexComponentBreadthPage(QWidget):
    ready = Signal(dict); failed = Signal(str)

    def __init__(self):
        super().__init__(); self.db = Database(); self.running = False; self.last_bucket = None
        layout = QVBoxLayout(self)
        title = QLabel("Index Component Breadth — Live Heat-map Direction"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("NIFTY, BANKNIFTY aur SENSEX components ko batched live quotes se count karta hai. 60% majority directional breadth hai; 80% se kam component coverage DATA GAP rahegi. Ye chart/OI confirmation hai, akela trade permission nahi.")
        note.setWordWrap(True); layout.addWidget(note)
        self.verdict = QLabel("Waiting for first live component snapshot…"); self.verdict.setObjectName("sectionTitle"); self.verdict.setWordWrap(True); layout.addWidget(self.verdict)
        self.market_direction = QLabel("Final market direction: waiting for Component + Chart + OI evidence…")
        self.market_direction.setObjectName("pageTitle"); self.market_direction.setWordWrap(True); layout.addWidget(self.market_direction)
        self.market_evidence = QLabel("Per-index evidence abhi available nahi hai.")
        self.market_evidence.setWordWrap(True); layout.addWidget(self.market_evidence)
        refresh = QPushButton("Refresh Component Breadth Now"); refresh.clicked.connect(lambda: self.scan(force=True)); layout.addWidget(refresh)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(("Time", "Index", "Verdict", "Positive", "Negative", "Flat", "Coverage", "Breadth %"))
        self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
        self.ready.connect(self._finished); self.failed.connect(self._failed)
        self.timer = QTimer(self); self.timer.setInterval(30_000); self.timer.timeout.connect(self.scan)
        self.refresh()

    def start_monitoring(self):
        if not self.timer.isActive(): self.timer.start()
        self.scan(force=True)

    def scan(self, _checked=False, force=False):
        now = datetime.now().astimezone(); session = market_session(now)
        bucket = (now.date(), now.hour, now.minute // 5)
        if self.running or not LiveSession.connected() or session["state"] != "OPEN": return
        if not force and (now.minute % 5 != 0 or now.second > 40 or bucket == self.last_bucket): return
        self.running = True; self.pending_bucket = bucket
        if not AnalysisScheduler.submit_unique("index-component-breadth", self._worker): self.running = False

    def _worker(self):
        db = Database()
        try: self.ready.emit(IndexComponentBreadthService(LiveSession.client, db).scan())
        except Exception as error: self.failed.emit(str(error))
        finally: db.close()

    def _finished(self, result):
        self.running = False; self.last_bucket = self.pending_bucket
        self.verdict.setText(f"Combined component verdict: {result['combined']['state']} | Coverage {result['combined']['coverage']} | Updated {datetime.now().strftime('%H:%M:%S')}")
        self.refresh()

    def _failed(self, message):
        self.running = False; self.verdict.setText(f"Component breadth DATA GAP: {message}")

    def refresh(self):
        rows = self.db.get_index_component_breadth(datetime.now().strftime("%d-%m-%Y")); self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = (str(row["captured_at"])[11:19], row["symbol"], row["state"], row["positive"], row["negative"], row["flat"],
                      f"{row['observed']}/{row['expected']} ({row['coverage']}%)", f"Green {row['positive_pct']:.1f}% | Red {row['negative_pct']:.1f}%")
            for j, value in enumerate(values): self.table.setItem(i, j, QTableWidgetItem(str(value)))
        if rows:
            latest = {s: next((r for r in rows if r["symbol"] == s), None) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
            latest_rows = [dict(row) for row in latest.values() if row]
            combined = combine_component_breadth(latest_rows)
            latest_time = max(str(row["captured_at"])[11:19] for row in latest_rows)
            detail = " | ".join(f"{s} {r['state']}" for s, r in latest.items() if r)
            self.verdict.setText(
                f"Combined component verdict: {combined['state']} | Last snapshot {latest_time} | {detail}"
            )
            candle_rows = self.db.get_index_candle_analyses(datetime.now().strftime("%d-%m-%Y"))
            latest_candles = {
                symbol: next((dict(row) for row in candle_rows if row["symbol"] == symbol), None)
                for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")
            }
            market = combine_market_evidence(
                [dict(row) for row in latest_rows],
                [row for row in latest_candles.values() if row],
            )
            evidence_time = str(market.get("last_evidence_at") or "-")
            if "T" in evidence_time:
                evidence_time = evidence_time.split("T", 1)[1][:8]
            self.market_direction.setText(
                f"Final market direction: {market['direction']} | Confirmed indices "
                f"{market['confirmed_indexes']}/3 | Evidence up to {evidence_time}"
            )
            self.market_evidence.setText("\n".join(
                f"{item['symbol']}: {item['direction']} | Components {item['component']} | "
                f"Chart {item['chart']} | OI {item['oi']} ({item['oi_quality']}/100)"
                for item in market["indexes"]
            ))
        else:
            self.market_direction.setText("Final market direction: DATA GAP — component snapshot unavailable")
            self.market_evidence.setText("Component + Chart + OI comparison ke liye live saved evidence nahi hai.")
