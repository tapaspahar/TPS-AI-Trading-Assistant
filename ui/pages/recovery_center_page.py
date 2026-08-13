"""Release 1.3 Overtrading Protection Center."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.overtrading_guard import EMOTIONAL_STATES, OvertradingGuard
from core.settings_store import SettingsStore


class RecoveryCenterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.guard = OvertradingGuard()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Overtrading Protection Center — Release 1.3")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Capital protection pehle. Ye center daily emotional check-in, one-paper-trade limit, "
            "consecutive-loss cooling lock aur paper-validation progress ko ek central hard guard me enforce karta hai. "
            "TPS ab bhi broker order place nahi karta."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        cards = QGridLayout()
        self.status = self._card("Today's guard")
        self.limit = self._card("Paper trades today")
        self.streak = self._card("Consecutive losses")
        self.validation = self._card("Paper validation")
        for index, card in enumerate((self.status, self.limit, self.streak, self.validation)):
            cards.addWidget(card[0], index // 2, index % 2)
        layout.addLayout(cards)

        check_box = QGroupBox("Daily Recovery check-in")
        form = QFormLayout(check_box)
        self.emotional_state = QComboBox()
        self.emotional_state.addItems(EMOTIONAL_STATES)
        self.paper_only = QCheckBox("Aaj main real-money order place nahi karunga; TPS sirf paper observation ke liye use hoga")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional: sleep, stress, urge ya accountability note")
        form.addRow("Current state", self.emotional_state)
        form.addRow(self.paper_only)
        form.addRow("Note", self.note)
        save = QPushButton("Save Today's Check-in")
        save.clicked.connect(self.save_check_in)
        form.addRow(save)
        layout.addWidget(check_box)

        rules = QLabel(
            "Active safeguards\n"
            "• Default maximum: 1 new paper trade per day in Recovery Mode.\n"
            "• 2 consecutive paper losses: 48-hour cooling lock.\n"
            "• STRESSED, ANGRY, FOMO or REVENGE state: new captures paused for the day.\n"
            "• At least 30 separate paper sessions are required before real-money eligibility can even be reviewed.\n"
            "• A score or signal can never override these behavioural and capital-protection locks."
        )
        rules.setWordWrap(True)
        layout.addWidget(rules)
        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(30_000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @staticmethod
    def _card(title):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        value = QLabel("—")
        value.setObjectName("cardValue")
        value.setWordWrap(True)
        layout.addWidget(value)
        return box, value

    def refresh(self):
        database = Database()
        try:
            assessment = self.guard.assess(SettingsStore().load(), database)
        finally:
            database.close()
        self.status[1].setText("READY — PAPER ONLY" if assessment["allowed"] else "LOCKED\n" + "\n".join(assessment["blockers"]))
        self.limit[1].setText(f"{assessment.get('paper_trades_today', 0)} / {assessment.get('daily_limit', 1)}")
        self.streak[1].setText(str(assessment.get("loss_streak", 0)))
        self.validation[1].setText(
            f"{assessment.get('paper_sessions', 0)} / {assessment.get('paper_session_target', 30)} sessions"
        )
        check_in = assessment.get("check_in")
        if check_in:
            index = self.emotional_state.findText(check_in.get("emotional_state", ""))
            if index >= 0:
                self.emotional_state.setCurrentIndex(index)
            self.paper_only.setChecked(bool(check_in.get("paper_only_commitment")))
            self.note.setText(check_in.get("note", ""))

    def save_check_in(self):
        try:
            saved = self.guard.save_check_in(
                self.emotional_state.currentText(), self.paper_only.isChecked(), self.note.text()
            )
        except ValueError as error:
            QMessageBox.warning(self, "Recovery check-in", str(error))
            return
        self.refresh()
        if saved["emotional_state"] == "CALM / STABLE" and saved["paper_only_commitment"]:
            QMessageBox.information(self, "Recovery check-in", "Check-in saved. Only bounded paper validation is available today.")
        else:
            QMessageBox.information(self, "Recovery check-in", "Check-in saved. New paper captures are paused for today; observation and reports remain available.")
