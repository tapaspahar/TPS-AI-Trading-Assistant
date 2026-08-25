"""Explainable, evidence-led TPS software improvement decision center."""

from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.self_development_decision import (
    ensure_completed_self_development_reviews,
    generate_and_save_self_development_review,
)
from services.development_validation import (
    build_counterfactual_review, build_evaluation_health, build_evidence_diagnostics,
)
from services.development_lifecycle import build_implementation_benefit_report
from core.settings_store import SettingsStore
from ui.widgets.excel_export_dialog import open_excel_export


class SelfDevelopmentPage(QWidget):
    """Permanent daily software-health reviews and human-approved suggestions."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.rows = []
        self.suggestions = []
        self.implementation_rows = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setMinimumHeight(1120)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 18)
        layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)
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
        finalize = QPushButton("Finalize Selected Review")
        finalize.clicked.connect(self.finalize_selected)
        controls.addWidget(finalize)
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
        self.coverage = self._card("Evaluation Coverage", "-")
        self.broker_health = self._card("Broker Reliability", "-")
        self.validation_samples = self._card("Confirmed Outcomes", "-")
        self.pipeline = self._card("Pipeline Evidence", "-")
        for column, card in enumerate((self.coverage, self.broker_health, self.validation_samples, self.pipeline)):
            cards.addWidget(card[0], 1, column)
        layout.addLayout(cards)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.date_list = QListWidget()
        self.date_list.setMinimumWidth(285)
        self.date_list.setMaximumWidth(360)
        self.date_list.currentItemChanged.connect(self.load_selected_review)
        splitter.addWidget(self.date_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self.status = QLabel()
        self.status.setWordWrap(True)
        right_layout.addWidget(self.status)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        suggestions_tab = QWidget()
        suggestions_layout = QVBoxLayout(suggestions_tab)
        suggestions_layout.setContentsMargins(4, 8, 4, 4)
        suggestions_layout.addWidget(QLabel("Development suggestions — select a row to review its evidence and approval test"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ("Priority", "Area", "Observation summary", "Implementation", "Review status")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.show_selected_suggestion)
        suggestions_layout.addWidget(self.table, 3)
        action_row = QHBoxLayout()
        reviewed = QPushButton("Mark Selected Reviewed")
        reviewed.clicked.connect(lambda: self.set_selected_status("REVIEWED"))
        reopen = QPushButton("Reopen Selected Suggestion")
        reopen.clicked.connect(lambda: self.set_selected_status("OPEN"))
        action_row.addWidget(reviewed)
        action_row.addWidget(reopen)
        suggestions_layout.addLayout(action_row)
        suggestions_layout.addWidget(QLabel("Selected suggestion — complete evidence and approval test"))
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(210)
        suggestions_layout.addWidget(self.details, 2)
        tabs.addTab(suggestions_tab, "Suggestions & Review")

        validation_tab = QWidget()
        validation_layout = QVBoxLayout(validation_tab)
        validation_layout.setContentsMargins(8, 10, 8, 8)
        validation_layout.addWidget(QLabel("Release 1.3 validation evidence — read-only; no production rule is changed here"))
        replay = QGridLayout()
        replay.addWidget(QLabel("Counterfactual score"), 0, 0)
        self.proposed_score = QSpinBox()
        self.proposed_score.setRange(0, 100)
        replay.addWidget(self.proposed_score, 0, 1)
        replay.addWidget(QLabel("Required confirmations"), 0, 2)
        self.proposed_matches = QSpinBox()
        self.proposed_matches.setRange(1, 10)
        replay.addWidget(self.proposed_matches, 0, 3)
        run_replay = QPushButton("Run Safe Counterfactual Replay")
        run_replay.clicked.connect(self.run_counterfactual)
        replay.addWidget(run_replay, 0, 4)
        replay.setColumnStretch(1, 1)
        replay.setColumnStretch(3, 1)
        replay.setColumnStretch(4, 2)
        validation_layout.addLayout(replay)
        self.validation_details = QPlainTextEdit()
        self.validation_details.setReadOnly(True)
        self.validation_details.setMinimumHeight(420)
        validation_layout.addWidget(self.validation_details, 1)
        tabs.addTab(validation_tab, "Validation Evidence & Replay")

        implementation_tab = QWidget()
        implementation_layout = QVBoxLayout(implementation_tab)
        implementation_layout.setContentsMargins(8, 10, 8, 8)
        implementation_intro = QLabel(
            "Suggestion-to-build audit: kya suggest hua, kis release mein build hua, aur replay/paper evidence se "
            "kya measurable fayda mila. Proof na ho toh report clearly MEASUREMENT PENDING dikhati hai."
        )
        implementation_intro.setWordWrap(True)
        implementation_layout.addWidget(implementation_intro)
        self.implementation_table = QTableWidget(0, 5)
        self.implementation_table.setHorizontalHeaderLabels(
            ("Suggestion", "Build status", "Release / build", "Benefit status", "Next action")
        )
        self.implementation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.implementation_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.implementation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.implementation_table.verticalHeader().setVisible(False)
        self.implementation_table.setAlternatingRowColors(True)
        implementation_header = self.implementation_table.horizontalHeader()
        implementation_header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            implementation_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.implementation_table.itemSelectionChanged.connect(self.show_selected_implementation)
        implementation_layout.addWidget(self.implementation_table, 3)
        implementation_layout.addWidget(QLabel("Selected lifecycle report — evidence, pending reason and next-release action"))
        self.implementation_details = QPlainTextEdit()
        self.implementation_details.setReadOnly(True)
        self.implementation_details.setMinimumHeight(230)
        implementation_layout.addWidget(self.implementation_details, 2)
        tabs.addTab(implementation_tab, "Implementation & Benefit Report")

        right_layout.addWidget(tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 1200])
        splitter.setMinimumHeight(610)
        layout.addWidget(splitter, 1)
        self.refresh(auto_generate=False)
        settings = SettingsStore().load()
        self.proposed_score.setValue(int(settings.get("trade_plan_min_score", 95)))
        self.proposed_matches.setValue(int(settings.get("tps_required_matches", 5)))

    @staticmethod
    def _card(title: str, value: str):
        shell = QWidget()
        shell.setObjectName("metricCard")
        shell.setMinimumHeight(82)
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
        for card in (self.coverage, self.broker_health, self.validation_samples, self.pipeline):
            card[1].setText("-")
        self.validation_details.setPlainText(message)
        self.implementation_table.setRowCount(0)
        self.implementation_details.setPlainText(message)

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
                suggestion.get("observation", ""), suggestion.get("implementation_status", "LEGACY / UNKNOWN"),
                suggestion.get("status", "OPEN"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, suggestion.get("key"))
                self.table.setItem(row_index, column, item)
        generated = str(row["generated_at"]).replace("T", " ")
        self.status.setText(
            f"Saved date: {trade_date} | {row['review_state']} revision {row['revision']} | "
            f"Build {row['build_id'] or '-'} | Generated: {generated} | Suggestions: {len(self.suggestions)} | Open: {open_items}"
        )
        self.refresh_validation_evidence(trade_date)
        self.refresh_implementation_report()
        if self.suggestions:
            self.table.selectRow(0)
        else:
            self.details.setPlainText(str(row["summary_text"]))

    def refresh_implementation_report(self):
        self.implementation_rows = build_implementation_benefit_report(self.db, self.suggestions)
        self.implementation_table.setRowCount(len(self.implementation_rows))
        for row_index, record in enumerate(self.implementation_rows):
            values = (
                record["suggestion"], record["build_status"], record["release"],
                record["benefit_status"], record["next_action"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.implementation_table.setItem(row_index, column, item)
        if self.implementation_rows:
            self.implementation_table.selectRow(0)
        else:
            self.implementation_details.setPlainText("Is review mein koi development suggestion save nahi hua.")

    def show_selected_implementation(self):
        index = self.implementation_table.currentRow()
        if index < 0 or index >= len(self.implementation_rows):
            return
        record = self.implementation_rows[index]
        self.implementation_details.setPlainText(
            f"SUGGESTION\n{record['suggestion']}\n\n"
            f"BUILD STATUS\n{record['build_status']}\nRelease/build: {record['release']}\n\n"
            f"BENEFIT STATUS\n{record['benefit_status']}\n{record['benefit']}\n\n"
            f"PENDING / NOT IMPLEMENTED REASON\n{record['reason']}\n\n"
            f"NEXT RELEASE ACTION\n{record['next_action']}\n\n"
            "Note: Cutie code present hone ko profit proof nahi maanti; benefit sirf saved replay ya paper-forward evidence se update hota hai."
        )

    def show_selected_suggestion(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.suggestions):
            return
        item = self.suggestions[index]
        self.details.setPlainText(
            f"[{item.get('priority')}] {item.get('area')}\nReview status: {item.get('status', 'OPEN')}\n"
            f"Implementation: {item.get('implementation_status', 'LEGACY / UNKNOWN')}\n\n"
            f"Observation:\n{item.get('observation')}\n\nSaved evidence:\n{item.get('evidence')}\n\n"
            f"Suggested development:\n{item.get('suggestion')}\n\n"
            f"Approval / validation test:\n{item.get('validation')}\n\n"
            "Cutie keh rahi hai: safety ke liye main source code ya production trading rules automatically modify nahi karungi."
        )

    def refresh_validation_evidence(self, trade_date: str):
        health = build_evaluation_health(self.db, trade_date, "ALL")
        evidence = build_evidence_diagnostics(self.db, trade_date)
        slots = health["evaluation"]
        broker = health["broker"]
        validation = health["validation"]
        self.coverage[1].setText(
            f"{slots['coverage_percent']:.1f}%\n{slots['evaluated_slots']}/{slots['expected_slots']} slots"
        )
        self.broker_health[1].setText(
            f"{broker['success_rate']:.1f}%\n{broker['requests']} request samples"
        )
        self.validation_samples[1].setText(
            f"{validation.get('samples', 0)} / 30\nAccuracy {validation.get('accuracy', 0):.1f}%"
        )
        pipeline_ready = slots["coverage_percent"] >= 95 and broker["requests"] > 0
        self.pipeline[1].setText("LIVE PROOF READY" if pipeline_ready else "EVIDENCE PENDING")
        volume = evidence["volume"]
        levels = evidence["levels"]
        outcomes = evidence["outcomes"]
        self.validation_details.setPlainText(
            "EVALUATION PIPELINE\n"
            f"Coverage: {slots['coverage_percent']:.1f}% | Evaluated {slots['evaluated_slots']} | "
            f"Gaps {slots['gap_slots']} | Reasons {slots['gap_reasons'] or 'none'}\n\n"
            "BROKER RELIABILITY\n"
            f"Requests {broker['requests']} | Success {broker['success_rate']:.1f}% | "
            f"Last good {broker.get('last_good_at') or '-'} | Data age {broker.get('last_good_data_age_seconds') or '-'} sec\n\n"
            "VOLUME / LEVEL EVIDENCE\n"
            f"Volume reason codes: {volume.get('reason_codes') or 'no samples'}\n"
            f"Regime split: {volume.get('regimes') or 'no samples'}\n"
            f"Level confluence: {levels.get('confluence') or 'no samples'} | "
            f"Average distance {levels.get('average_distance_atr') or '-'} ATR | "
            f"Average age {levels.get('average_age_seconds') or '-'} sec\n\n"
            "OUTCOME POST-MORTEM\n"
            f"Closed samples {outcomes.get('samples', 0)} | Decisive {outcomes.get('decisive_samples', 0)} | "
            f"Avg entry lateness {outcomes.get('average_entry_lateness_seconds') or '-'} sec | "
            f"Avg spread {outcomes.get('average_premium_spread_percent') or '-'}% | "
            f"Avg MAE {outcomes.get('average_mae') or '-'} | Avg MFE {outcomes.get('average_mfe') or '-'}\n\n"
            "Approval gates remain evidence-led: 3 consecutive sessions at 95%+ coverage and "
            "30 confirmed outcomes cannot be fabricated by software."
        )

    def run_counterfactual(self):
        trade_date = self.date_input.date().toString("dd-MM-yyyy")
        try:
            review = build_counterfactual_review(
                self.db, trade_date, self.proposed_score.value(), self.proposed_matches.value(),
            )
        except ValueError as error:
            QMessageBox.information(self, "Counterfactual replay", str(error))
            return
        self.validation_details.setPlainText(
            f"SAFE COUNTERFACTUAL REPLAY — {trade_date}\n"
            f"Saved evaluations: {review['attempts']}\n"
            f"Current rule candidates: {review['current_candidate_count']}\n"
            f"Proposed rule candidates: {review['proposed_candidate_count']}\n"
            f"Additional review-only candidates: {review['additional_candidate_count']}\n"
            f"Hard-blocked candidates remain blocked: {review['hard_blocked_count']}\n\n"
            f"One-blocker trials: {len(review['one_blocker_trials'])} | Outcomes: {review['outcome_summary']}\n\n"
            "This comparison does not alter production settings. Forward outcomes and false-entry rate "
            "must validate any future threshold change."
        )

    def finalize_selected(self):
        item = self.date_list.currentItem()
        if item is None:
            return
        trade_date = str(item.data(Qt.UserRole))
        if self.db.finalize_self_development_review(trade_date):
            self.status.setText(f"{trade_date} review FINAL mark ho gaya. Source evidence badalne par naya DRAFT revision banega.")
            self.refresh(auto_generate=False)

    def set_selected_status(self, status: str):
        date_item = self.date_list.currentItem()
        row_index = self.table.currentRow()
        if date_item is None or row_index < 0 or row_index >= len(self.suggestions):
            return
        trade_date = str(date_item.data(Qt.UserRole))
        key = str(self.suggestions[row_index].get("key") or "")
        if key and self.db.update_self_development_suggestion_status(trade_date, key, status):
            self.refresh(auto_generate=False)
