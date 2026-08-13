"""Permanent candle-by-candle audit page for automatic paper trading."""
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.auto_attempt_report import format_auto_paper_attempt


class AutoAttemptReportPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.rows = []
        layout = QVBoxLayout(self)
        title = QLabel("Auto Trade Attempt Report — permanent 5-minute candle audit")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Every saved evaluation is shown here whether a paper trade was captured, rejected, or blocked by a safety limit."))

        actions = QHBoxLayout()
        today = QPushButton("Today's Attempts")
        today.clicked.connect(lambda: self.refresh(today_only=True))
        all_rows = QPushButton("All Attempts")
        all_rows.clicked.connect(lambda: self.refresh(today_only=False))
        export = QPushButton("Export Attempts to CSV")
        export.clicked.connect(self.export_csv)
        actions.addWidget(today); actions.addWidget(all_rows); actions.addWidget(export)
        layout.addLayout(actions)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels((
            "Candle time", "Checked at", "Symbol", "Outcome", "Timing stage", "Delay", "Decision",
            "Confirmations", "Score",
        ))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_selected_attempt)
        layout.addWidget(self.table, 1)

        layout.addWidget(QLabel("Selected attempt — complete values and reasons"))
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(240)
        layout.addWidget(self.details, 1)
        self.today_only = True
        self.refresh()

    def refresh(self, today_only=None):
        if today_only is not None:
            self.today_only = bool(today_only)
        trade_date = datetime.now().strftime("%d-%m-%Y") if self.today_only else None
        self.rows = self.db.get_auto_trade_attempts(trade_date)
        self.table.setRowCount(len(self.rows))
        captured = sum(row["outcome"] == "TRADE CAPTURED" for row in self.rows)
        early_watches = sum((row["timing_stage"] or "") == "EARLY WATCH" for row in self.rows)
        first_valid = sum((row["timing_stage"] or "") == "FIRST VALID" for row in self.rows)
        measured_delays = [row["timing_delay_seconds"] for row in self.rows if row["timing_delay_seconds"] is not None]
        for index, row in enumerate(self.rows):
            confirmations = "-" if row["confirmations_passed"] is None else f"{row['confirmations_passed']}/{row['confirmations_total']}"
            values = (
                row["candle_time"] or "Not evaluated", row["checked_at"], row["symbol"], row["outcome"],
                row["timing_stage"] or "NONE",
                "-" if row["timing_delay_seconds"] is None else f"{row['timing_delay_seconds']} sec",
                row["decision"] or row["status_text"], confirmations,
                "-" if row["score"] is None else f"{row['score']}/100",
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        scope = "today" if self.today_only else "all saved dates"
        average_delay = "-" if not measured_delays else f"{sum(measured_delays) / len(measured_delays):.0f} sec"
        self.summary.setText(
            f"Showing {len(self.rows)} attempts for {scope} | Early Watch: {early_watches} | "
            f"First Valid: {first_valid} | Captured: {captured} | Average discovery-to-valid/capture delay: {average_delay} | "
            f"Not captured/skipped: {len(self.rows) - captured}"
        )
        if self.rows:
            self.table.selectRow(0)
        else:
            self.details.setPlainText("No automatic candle evaluations have been saved for this view. Enable Auto Paper Trading during market hours.")

    def show_selected_attempt(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            return
        try:
            result = json.loads(self.rows[row]["details_json"])
            self.details.setPlainText(format_auto_paper_attempt(result))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self.details.setPlainText(f"Saved attempt details could not be read: {error}")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Auto Trade Attempts", "auto_trade_attempts.csv", "CSV files (*.csv)")
        if not path:
            return
        trade_date = datetime.now().strftime("%d-%m-%Y") if self.today_only else None
        try:
            count = self.db.export_auto_trade_attempts(path, trade_date)
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} automatic trade attempt(s) to CSV.")
