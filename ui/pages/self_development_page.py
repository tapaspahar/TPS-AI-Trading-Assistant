"""Explainable, evidence-led TPS software improvement decision center."""

from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.self_development_decision import (
    ensure_completed_self_development_reviews,
    generate_and_save_self_development_review,
)
from ui.widgets.excel_export_dialog import open_excel_export


class SelfDevelopmentPage(QWidget):
    """Permanent daily software-health reviews and human-approved suggestions."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.rows = []
        self.suggestions = []
        layout = QVBoxLayout(self)
        title = QLabel("AI Self-Development Decision Center")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Market close ke baad TPS saved attempts, data gaps, blockers aur trade outcomes audit karke "
            "development rectification suggestions deta hai. AI code ya strategy rules khud change nahi karta; "
            "har change replay, paper forward-test aur human approval ke baad hi consider hoga."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Trading date"))
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        controls.addWidget(self.date_input)
        generate = QPushButton("Generate / Update AI Review")
        generate.clicked.connect(self.generate_selected)
        controls.addWidget(generate)
        refresh = QPushButton("Refresh Saved Reviews")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        excel = QPushButton("Export Excel by Date / Period")
        excel.clicked.connect(lambda: open_excel_export(self, self.db, "self_development"))
        controls.addWidget(excel)
        layout.addLayout(controls)
        cards = QGridLayout()
        self.health = self._card("System Health", "-")
        self.verdict = self._card("AI Verdict", "No review")
        self.open_count = self._card("Open Suggestions", "0")
        self.evidence = self._card("Evidence Rule", "Repeated proof")
        for column, card in enumerate((self.health, self.verdict, self.open_count, self.evidence)):
            cards.addWidget(card[0], 0, column)
        layout.addLayout(cards)
        splitter = QSplitter()
        self.date_list = QListWidget()
        self.date_list.setMinimumWidth(270)
        self.date_list.currentItemChanged.connect(self.load_selected_review)
        splitter.addWidget(self.date_list)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.status = QLabel()
        self.status.setWordWrap(True)
        right_layout.addWidget(self.status)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ("Priority", "Area", "Observation", "Evidence", "Development suggestion", "Status")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_selected_suggestion)
        right_layout.addWidget(self.table, 2)
        action_row = QHBoxLayout()
        reviewed = QPushButton("Mark Selected Reviewed")
        reviewed.clicked.connect(lambda: self.set_selected_status("REVIEWED"))
        reopen = QPushButton("Reopen Selected Suggestion")
        reopen.clicked.connect(lambda: self.set_selected_status("OPEN"))
        action_row.addWidget(reviewed)
        action_row.addWidget(reopen)
        right_layout.addLayout(action_row)
        right_layout.addWidget(QLabel("Selected suggestion - evidence and approval test"))
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(150)
        right_layout.addWidget(self.details, 1)
        splitter.addWidget(right)
        splitter.setSizes([280, 1100])
        layout.addWidget(splitter, 1)
        self.refresh(auto_generate=False)

    @staticmethod
    def _card(title: str, value: str):
        shell = QWidget()
        shell.setObjectName("metricCard")
        card_layout = QVBoxLayout(shell)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setWordWrap(True)
        card_layout.addWidget(heading)
        card_layout.addWidget(value_label)
        return shell, value_label

    def refresh(self, _checked: bool = False, auto_generate: bool = True):
        if auto_generate:
            ensure_completed_self_development_reviews(self.db)
        selected = self.date_input.date().toString("dd-MM-yyyy")
        self.rows = self.db.get_self_development_reviews()
        self.date_list.blockSignals(True)
        self.date_list.clear()
        selected_item = None
        for row in self.rows:
            suggestions = json.loads(row["suggestions_json"] or "[]")
            open_items = sum(item.get("status", "OPEN") == "OPEN" for item in suggestions)
            item = QListWidgetItem(f"{row['trade_date']} | health {row['health_score']}/100 | open {open_items}")
            item.setData(Qt.UserRole, row["trade_date"])
            self.date_list.addItem(item)
            if row["trade_date"] == selected:
                selected_item = item
        self.date_list.blockSignals(False)
        if selected_item is None and self.date_list.count():
            selected_item = self.date_list.item(0)
        if selected_item:
            self.date_list.setCurrentItem(selected_item)
            self.load_selected_review(selected_item)
        else:
            self._clear_review("Post Market Analysis complete hone ke baad daily AI review yahan save hoga.")

    def _clear_review(self, message: str):
        self.table.setRowCount(0)
        self.details.setPlainText(message)
        self.status.setText(message)
        self.health[1].setText("-")
        self.verdict[1].setText("No review")
        self.open_count[1].setText("0")

    def generate_selected(self):
        trade_date = self.date_input.date().toString("dd-MM-yyyy")
        if self.db.get_post_market_tps_analysis(trade_date) is None:
            QMessageBox.information(
                self, "AI Self-Development Decision Center",
                "Is date ka Post Market Analysis of TPS available nahi hai. Pehle post-market report generate karein.",
            )
            return
        review = generate_and_save_self_development_review(self.db, trade_date)
        self.status.setText(f"{trade_date} ka evidence-led AI development review update ho gaya. ID: {review['id']}.")
        self.refresh(auto_generate=False)

    def load_selected_review(self, current, _previous=None):
        if current is None:
            return
        trade_date = str(current.data(Qt.UserRole))
        try:
            parsed = datetime.strptime(trade_date, "%d-%m-%Y")
            self.date_input.setDate(QDate(parsed.year, parsed.month, parsed.day))
        except ValueError:
            pass
        row = self.db.get_self_development_review(trade_date)
        if row is None:
            return
        self.suggestions = json.loads(row["suggestions_json"] or "[]")
        open_items = sum(item.get("status", "OPEN") == "OPEN" for item in self.suggestions)
        self.health[1].setText(f"{row['health_score']} / 100")
        self.verdict[1].setText(str(row["verdict"]))
        self.open_count[1].setText(str(open_items))
        self.evidence[1].setText("Replay + forward test")
        self.table.setRowCount(len(self.suggestions))
        for row_index, suggestion in enumerate(self.suggestions):
            values = (
                suggestion.get("priority", ""), suggestion.get("area", ""),
                suggestion.get("observation", ""), suggestion.get("evidence", ""),
                suggestion.get("suggestion", ""), suggestion.get("status", "OPEN"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, suggestion.get("key"))
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        generated = str(row["generated_at"]).replace("T", " ")
        self.status.setText(
            f"Saved date: {trade_date} | Generated: {generated} | Suggestions: {len(self.suggestions)} | Open: {open_items}"
        )
        if self.suggestions:
            self.table.selectRow(0)
        else:
            self.details.setPlainText(str(row["summary_text"]))

    def show_selected_suggestion(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.suggestions):
            return
        item = self.suggestions[index]
        self.details.setPlainText(
            f"[{item.get('priority')}] {item.get('area')}\nStatus: {item.get('status', 'OPEN')}\n\n"
            f"Observation:\n{item.get('observation')}\n\nSaved evidence:\n{item.get('evidence')}\n\n"
            f"Suggested development:\n{item.get('suggestion')}\n\n"
            f"Approval / validation test:\n{item.get('validation')}\n\n"
            "Safety: TPS will not modify source code or production trading rules automatically."
        )

    def set_selected_status(self, status: str):
        date_item = self.date_list.currentItem()
        row_index = self.table.currentRow()
        if date_item is None or row_index < 0 or row_index >= len(self.suggestions):
            return
        trade_date = str(date_item.data(Qt.UserRole))
        key = str(self.suggestions[row_index].get("key") or "")
        if key and self.db.update_self_development_suggestion_status(trade_date, key, status):
            self.refresh(auto_generate=False)
