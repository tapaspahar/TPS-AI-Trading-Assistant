"""Smart five-minute options/chart/OI memory viewer."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.database_manager import Database
from services.options_memory_service import build_options_memory_view


class OptionsMemoryPage(QWidget):
    def __init__(self):
        super().__init__(); self.db = Database()
        layout = QVBoxLayout(self)
        title = QLabel("Smart Options Memory — 5-Minute Chart, Volume & OI/COI Learning"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel("Har completed 5-minute index-future candle aur nearby option OI/COI evidence permanent memory se read hota hai. Current condition previous market days se compare hoti hai; similarity aur follow-rate guaranteed direction nahi hain.")
        note.setWordWrap(True); layout.addWidget(note)
        controls = QHBoxLayout(); self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX")); self.symbol.currentTextChanged.connect(self._refresh_if_visible)
        refresh = QPushButton("Refresh Current vs Historical Memory"); refresh.clicked.connect(self.refresh)
        controls.addWidget(QLabel("Index")); controls.addWidget(self.symbol); controls.addWidget(refresh, 1); layout.addLayout(controls)
        self.summary = QLabel(); self.summary.setWordWrap(True); self.summary.setObjectName("sectionTitle"); layout.addWidget(self.summary)
        self.current = QTableWidget(0, 13); self.current.setHorizontalHeaderLabels(("Time", "Pattern", "Direction", "Move", "Volume", "Aggression", "ATM", "ATM CE", "ATM PE", "OI flow", "Call COI", "Put COI", "Coverage"))
        self.current.setHorizontalScrollBarPolicy(self.current.horizontalScrollBarPolicy()); layout.addWidget(self.current, 2)
        layout.addWidget(QLabel("Closest historical 5-minute situations and what happened in the next candle"))
        self.analogs = QTableWidget(0, 7); self.analogs.setHorizontalHeaderLabels(("Date", "Time", "Similarity", "Pattern", "OI flow", "Next move", "Next direction")); layout.addWidget(self.analogs, 1)
        self.timer = QTimer(self); self.timer.setInterval(30_000); self.timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.timer.isActive():
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _refresh_if_visible(self, *_args):
        if self.isVisible():
            self.refresh()

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values): table.setItem(r, c, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def refresh(self, *_args):
        view = build_options_memory_view(self.db, self.symbol.currentText())
        self.summary.setText(
            f"{view['state']} | Historical direction: {view['predicted_direction']} | "
            f"Follow-rate {view['historical_follow_rate']:.1f}% from {view['meaningful_samples']} comparable samples. {view['note']}"
        )
        self._fill(self.current, [(str(r['candle_time'])[11:16], r['pattern'], r['direction'], f"{float(r['move_points'] or 0):+.2f}",
                                   f"{float(r['volume_ratio'] or 0):.2f}x" if r['volume_ratio'] is not None else "DATA GAP", r['aggression'],
                                   r.get('atm_strike') or "-", r.get('atm_ce_premium') or "-", r.get('atm_pe_premium') or "-", r['oi_direction'],
                                   f"{float(r['call_coi'] or 0):+,.0f}", f"{float(r['put_coi'] or 0):+,.0f}", f"{int(r['source_completeness'] or 0)}%") for r in view['rows']])
        self._fill(self.analogs, [(a['trade_date'], str(a['candle_time'])[11:16], f"{a['similarity']:.1f}%", a['pattern'], a['oi_direction'], f"{a['next_move']:+.2f}", a['next_direction']) for a in view['analogs']])
