"""Trend Memory Monitor: daily fingerprints and historical analog evidence."""

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.trend_memory_service import ensure_completed_trend_memories, load_trend_memory_view


class TrendMemoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.rows = []
        layout = QVBoxLayout(self)
        title = QLabel("Trend Memory Monitor")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Har trading day ka trend, chart shape, Candle DNA, indicator/OI context aur actual outcome permanent database mein save hota hai. "
            "Similarity score historical resemblance hai, guaranteed prediction nahi."
        ))
        controls = QHBoxLayout()
        self.symbol = QComboBox()
        self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.symbol.currentTextChanged.connect(self.refresh)
        refresh = QPushButton("Refresh & Match Historical Patterns")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(QLabel("Index")); controls.addWidget(self.symbol, 1); controls.addWidget(refresh, 2)
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Date", "Trend", "Chart pattern", "Candle DNA", "Move", "Range", "Snapshots"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_selected)
        layout.addWidget(self.table, 2)
        layout.addWidget(QLabel("Selected historical day — actual outcome and saved market fingerprint"))
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(170)
        layout.addWidget(self.details, 1)
        self.refresh()

    def refresh(self, *_args):
        ensure_completed_trend_memories(self.db)
        self.rows, live = load_trend_memory_view(self.db, self.symbol.currentText())
        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            values = (
                row["trade_date"], row["trend"], row["chart_pattern"], row["candle_signature"],
                f"{float(row['return_pct']):+.2f}%", f"{float(row['range_pct']):.2f}%", row["snapshot_count"],
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        if live and live[0]["matches"]:
            best = live[0]["matches"][0]
            self.summary.setText(
                f"Saved market days: {len(self.rows)} | Aaj ka closest analog: {best['trade_date']} — "
                f"{best['similarity']:.1f}% similar | Us din: {best['outcome_text']}"
            )
        else:
            self.summary.setText(
                f"Saved market days: {len(self.rows)} | Live match ke liye aaj ke kam-se-kam 6 saved 5-minute observations chahiye."
            )
        if self.rows:
            self.table.selectRow(0)
        else:
            self.details.setPlainText("Abhi koi completed trading-day fingerprint available nahi hai. Market Snapshot recorder data collect karne ke baad yahan history banegi.")

    def show_selected(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows[index]
        f = row.get("features") or {}
        self.details.setPlainText(
            f"Date: {row['trade_date']} | Symbol: {row['symbol']}\n"
            f"Trend: {row['trend']} | Pattern: {row['chart_pattern']} | Candle DNA: {row['candle_signature']}\n"
            f"EMA: {f.get('ema_state', '-')} | VWAP: {f.get('vwap_state', '-')} | SuperTrend: {f.get('supertrend_state', '-')} | "
            f"Volume: {f.get('volume_state', '-')} | RSI: {f.get('rsi', '-')} | OI-PCR: {f.get('oi_pcr', '-')}\n\n"
            f"Actual outcome: {row['outcome_text']}"
        )
