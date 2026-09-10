"""Broker-synced open-position intelligence and durable order history."""
from __future__ import annotations

from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.live_session import LiveSession
from services.order_intelligence import OrderIntelligenceService


class OrderIntelligencePage(QWidget):
    scan_ready = Signal(dict)
    scan_failed = Signal(str)

    def __init__(self):
        super().__init__(); self.rows = []; self.scanning = False
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(18, 16, 18, 22)
        title = QLabel("Broker Order Intelligence — Live Positions & Synced History"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "Cutie connected broker ke sirf non-zero open positions/pending orders ka live analysis karti hai. "
            "Completed, cancelled aur rejected orders broker se sync hokar neeche history me preserve rehte hain. "
            "Linked target/stop unavailable ho toh software unhe invent nahi karega; broker position aur risk controls final source rahenge."
        ); note.setWordWrap(True); layout.addWidget(note)
        self.status = QLabel("Broker connect hone ke baad auto-sync hoga."); self.status.setWordWrap(True); layout.addWidget(self.status)
        refresh = QPushButton("Sync Broker Orders Now"); refresh.clicked.connect(self.refresh); layout.addWidget(refresh)
        layout.addWidget(QLabel("Open positions / pending orders — live analysis"))
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(("Order", "Symbol", "Side", "Qty", "Status", "Entry", "Market", "P/L pts", "MFE", "MAE", "Cutie review"))
        self.table.setMinimumHeight(300); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel); self.table.itemSelectionChanged.connect(self.show_selected)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Selected order — complete evidence and hindsight limits"))
        self.detail = QLabel("Select an order row."); self.detail.setWordWrap(True); self.detail.setMinimumHeight(150); layout.addWidget(self.detail)
        layout.addWidget(QLabel("Closed / completed broker order history — synchronized record"))
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(("Synced at", "Order", "Symbol", "Side", "Qty", "Final status"))
        self.history.setMinimumHeight(260); self.history.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history.setHorizontalScrollMode(QTableWidget.ScrollPerPixel); layout.addWidget(self.history)
        scroll.setWidget(body); outer.addWidget(scroll)
        self.scan_ready.connect(self._show_results); self.scan_failed.connect(self._show_error)
        self.timer = QTimer(self); self.timer.setInterval(30_000); self.timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.timer.isActive():
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if not LiveSession.connected() or LiveSession.broker_id != "angel_one":
            self.status.setText("Connected broker session available nahi hai. Settings se broker connect karein."); return
        if self.scanning: return
        self.scanning = True; self.status.setText("Broker positions aur final order history sync ho rahe hain…")
        Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        database = None
        try:
            database = Database()
            self.scan_ready.emit(OrderIntelligenceService(LiveSession.client, database).scan())
        except Exception as error: self.scan_failed.emit(str(error))
        finally:
            if database is not None: database.close()

    def _show_error(self, message):
        self.scanning = False; self.status.setText(f"Order-book scan unavailable: {message}")

    def _show_results(self, payload):
        self.scanning = False; self.rows = list(payload.get("open") or [])
        database = Database()
        try: history_rows = database.get_closed_order_intelligence_history()
        finally: database.close()
        self.status.setText(
            f"Open analysis {len(self.rows)} | Closed history {len(history_rows)} | Auto-sync every 30 seconds"
        )
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            values = (row["broker_order_id"], row["trading_symbol"], row["side"], row["quantity"], row["order_status"],
                      row["entry_price"], row["market_price"], row["unrealized_points"], row["mfe_points"], row["mae_points"], row["analysis_state"])
            for c, value in enumerate(values): self.table.setItem(r, c, QTableWidgetItem("-" if value is None else str(value)))
        self.table.resizeColumnsToContents()
        if self.rows: self.table.selectRow(0)
        else: self.detail.setText("Koi non-zero open broker position ya pending order nahi hai.")
        self.history.setRowCount(len(history_rows))
        for r, row in enumerate(history_rows):
            try: details = __import__("json").loads(row.get("details_json") or "{}")
            except (TypeError, ValueError): details = {}
            values = (row.get("captured_at"), row.get("broker_order_id"), row.get("trading_symbol"),
                      details.get("side", "-"), details.get("quantity", "-"), row.get("order_status"))
            for c, value in enumerate(values): self.history.setItem(r, c, QTableWidgetItem(str(value)))
        self.history.resizeColumnsToContents()

    def show_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows): return
        item = self.rows[row]
        self.detail.setText(
            f"Cutie state: {item['analysis_state']}\n{item['explanation']}\n\n"
            f"Entry ₹{item['entry_price'] or 0:,.2f} | Current ₹{item['market_price'] or 0:,.2f} | "
            f"Move {item['unrealized_points'] if item['unrealized_points'] is not None else '-'} points\n"
            + "\n".join(f"• {text}" for text in item["evidence"])
            + "\n\nRukna chahiye tha ya exit better tha ka final hindsight tabhi valid hoga jab entry ke baad complete candles, actual fills, target aur stop evidence available ho."
        )
