"""Permanent, searchable-in-session history of delivered TPS notifications."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.notification_service import NOTIFICATION_LABELS


class NotificationCenterPage(QWidget):
    """Show every alert delivered by TPS with its timestamp and read state."""

    unread_count_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.rows = []
        self.scope = "today"

        layout = QVBoxLayout(self)
        title = QLabel("Notification Center — permanent TPS alert history")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Every desktop notification delivered by TPS is saved here with date, time, category and complete message. "
            "This history remains available after restart and software updates."
        ))

        actions = QHBoxLayout()
        today = QPushButton("Today's Notifications")
        today.clicked.connect(lambda: self.set_scope("today"))
        all_rows = QPushButton("All Notifications")
        all_rows.clicked.connect(lambda: self.set_scope("all"))
        unread = QPushButton("Unread Only")
        unread.clicked.connect(lambda: self.set_scope("unread"))
        self.mark_selected_button = QPushButton("Mark Selected Read")
        self.mark_selected_button.clicked.connect(self.mark_selected_read)
        mark_all = QPushButton("Mark All Read")
        mark_all.clicked.connect(self.mark_all_read)
        export = QPushButton("Export CSV")
        export.clicked.connect(self.export_csv)
        clean = QPushButton("Clean Repeated Alerts")
        clean.clicked.connect(self.clean_repeated_alerts)
        for button in (today, all_rows, unread, self.mark_selected_button, mark_all, export, clean):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Date & time", "Status", "Category / page", "Title", "Message"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.itemDoubleClicked.connect(lambda _item: self.mark_selected_read())
        layout.addWidget(self.table, 1)

        layout.addWidget(QLabel("Selected notification — complete saved details"))
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(150)
        layout.addWidget(self.details)
        self.refresh()

    def set_scope(self, scope: str):
        self.scope = scope
        self.refresh()

    @staticmethod
    def _display_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(str(value)).astimezone()
            return parsed.strftime("%d-%m-%Y %H:%M:%S %Z")
        except (TypeError, ValueError):
            return str(value)

    def refresh(self, *_args):
        self.rows = self.db.get_notifications(
            today_only=self.scope == "today", unread_only=self.scope == "unread"
        )
        unread_count = self.db.get_unread_notification_count()
        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            category = NOTIFICATION_LABELS.get(row["category"], row["category"].replace("_", " ").title())
            values = (
                self._display_time(row["created_at"]),
                "READ" if row["is_read"] else "UNREAD",
                category,
                row["title"],
                row["message"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if not row["is_read"]:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        scope_text = {"today": "today", "all": "all saved dates", "unread": "unread alerts"}[self.scope]
        self.summary.setText(
            f"Showing {len(self.rows)} notification(s) for {scope_text} | Total unread: {unread_count}"
        )
        self.unread_count_changed.emit(unread_count)
        if self.rows:
            self.table.selectRow(0)
        else:
            self.details.setPlainText("No saved notifications are available for this view.")

    def show_selected(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows[index]
        category = NOTIFICATION_LABELS.get(row["category"], row["category"])
        self.details.setPlainText(
            f"Date & time: {self._display_time(row['created_at'])}\n"
            f"Status: {'READ' if row['is_read'] else 'UNREAD'}\n"
            f"Category / page: {category}\n"
            f"Title: {row['title']}\n\n{row['message']}"
        )

    def mark_selected_read(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        self.db.mark_notification_read(self.rows[index]["id"])
        self.refresh()

    def mark_all_read(self):
        self.db.mark_all_notifications_read()
        self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export TPS Notifications", "tps_notifications.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            count = self.db.export_notifications(
                path, today_only=self.scope == "today", unread_only=self.scope == "unread"
            )
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} notification(s) to CSV.")

    def clean_repeated_alerts(self):
        answer = QMessageBox.question(
            self, "Clean repeated alerts",
            "Purane repeated Support/Resistance, Auto Opportunity aur exact duplicate alerts remove karein? "
            "Har daily event ka pehla record safe rahega.",
        )
        if answer != QMessageBox.Yes:
            return
        removed = self.db.remove_repeated_notifications()
        self.refresh()
        QMessageBox.information(self, "Cleanup complete", f"{removed} repeated alert record(s) remove hue.")
