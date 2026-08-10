"""Permanent date-wise Roman Hindi post-market TPS journal page."""

from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.database_manager import Database
from services.post_market_tps_analysis import ensure_completed_post_market_reports, generate_and_save_post_market_analysis


class PostMarketTpsAnalysisPage(QWidget):
    """A durable, readable journal of daily TPS auto-trade outcomes."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        layout = QVBoxLayout(self)
        title = QLabel("Post Market Analysis of TPS")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Har trading date ka Roman Hindi audit: trade liya ya nahi, kis wajah se, kitni candles check hui aur system/data gap kahan tha."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Trading date"))
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        controls.addWidget(self.date_input)
        self.generate_button = QPushButton("Analysis Generate / Update Karein")
        self.generate_button.clicked.connect(self.generate_selected)
        controls.addWidget(self.generate_button)
        refresh_button = QPushButton("Saved Dates Refresh Karein")
        refresh_button.clicked.connect(self.refresh)
        controls.addWidget(refresh_button)
        layout.addLayout(controls)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        splitter = QSplitter()
        self.date_list = QListWidget()
        self.date_list.setMinimumWidth(230)
        self.date_list.currentItemChanged.connect(self.load_selected_item)
        splitter.addWidget(self.date_list)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.report.setPlaceholderText("Saved post-market analysis yahan dikhega.")
        splitter.addWidget(self.report)
        splitter.setSizes([260, 1000])
        layout.addWidget(splitter, 1)
        self.refresh(auto_generate=False)

    def _source_signature(self, trade_date: str) -> tuple[int, int, int, str]:
        attempts = self.db.get_auto_trade_attempts(trade_date, limit=5000)
        trades = self.db.get_trades_for_date(trade_date)
        snapshots = self.db.get_market_snapshots(trade_date)
        latest = max((str(row["checked_at"]) for row in attempts), default="")
        return len(attempts), len(trades), len(snapshots), latest

    def refresh(self, _checked: bool = False, auto_generate: bool = True):
        if auto_generate:
            ensure_completed_post_market_reports(self.db)
        selected_date = self.date_input.date().toString("dd-MM-yyyy")
        self.date_list.blockSignals(True)
        self.date_list.clear()
        selected_item = None
        for row in self.db.get_post_market_tps_analyses():
            try:
                metrics = json.loads(row["metrics_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                metrics = {}
            label = (
                f"{row['trade_date']}  |  trades {int(metrics.get('captured', 0))}  |  "
                f"attempts {int(metrics.get('source_attempt_count', 0))}"
            )
            item = QListWidgetItem(label)
            item.setData(256, row["trade_date"])
            self.date_list.addItem(item)
            if row["trade_date"] == selected_date:
                selected_item = item
        self.date_list.blockSignals(False)
        if selected_item is None and self.date_list.count():
            selected_item = self.date_list.item(0)
        if selected_item:
            self.date_list.setCurrentItem(selected_item)
            self.load_selected_item(selected_item)
        else:
            self.report.clear()
            self.status.setText("Abhi koi saved TPS post-market analysis nahi hai.")

    def generate_selected(self):
        trade_date = self.date_input.date().toString("dd-MM-yyyy")
        signature = self._source_signature(trade_date)
        if not any(signature[:3]):
            QMessageBox.information(
                self,
                "Post Market Analysis of TPS",
                "Is date ke liye auto attempts, trades ya market snapshots available nahi hain.",
            )
            return
        analysis = generate_and_save_post_market_analysis(self.db, trade_date)
        self.status.setText(f"{trade_date} ka analysis save/update ho gaya. Record ID: {analysis['id']}.")
        self.refresh(auto_generate=False)

    def load_selected_item(self, current, _previous=None):
        if current is None:
            return
        trade_date = str(current.data(256))
        parsed = datetime.strptime(trade_date, "%d-%m-%Y")
        self.date_input.setDate(QDate(parsed.year, parsed.month, parsed.day))
        row = self.db.get_post_market_tps_analysis(trade_date)
        if row:
            self.report.setPlainText(str(row["summary_text"]))
            generated = datetime.fromisoformat(str(row["generated_at"])).strftime("%d-%m-%Y %H:%M:%S")
            self.status.setText(f"Saved date: {trade_date} | Last generated: {generated}")
