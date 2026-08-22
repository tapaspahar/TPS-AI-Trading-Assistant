"""Overtrading protection and bounded paper-validation testing controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from core.overtrading_guard import EMOTIONAL_STATES, OvertradingGuard
from core.settings_store import SettingsStore


class RecoveryCenterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.guard = OvertradingGuard()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("recoveryCenterScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        content = QWidget()
        content.setObjectName("recoveryCenterScrollContent")
        # Preserve each section's usable height. On shorter windows the page
        # scrolls instead of forcing form rows, cards and buttons to overlap.
        content.setMinimumHeight(980)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

        title = QLabel("Overtrading Protection & Paper Validation Center — Release 1.4.4")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Capital protection pehle. Normal mode daily emotional check-in, bounded paper limit aur "
            "consecutive-loss cooling lock enforce karta hai. Temporary testing mode accuracy validation ke liye "
            "maximum 20 simulated trades/day allow kar sakta hai. "
            "TPS ab bhi broker order place nahi karta."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        testing_box = QGroupBox("Paper Validation Testing Mode")
        testing_box.setMinimumHeight(205)
        testing_form = QFormLayout(testing_box)
        self.testing_mode = QCheckBox(
            "Temporary testing mode ON — recovery/overtrading locks suspend karein (sirf paper trades)"
        )
        self.testing_limit = QSpinBox()
        self.testing_limit.setRange(1, 20)
        self.testing_limit.setValue(20)
        self.testing_limit.setSuffix(" paper trades/day")
        self.testing_controls_dirty = False
        self.testing_mode.toggled.connect(self._mark_testing_controls_dirty)
        self.testing_limit.valueChanged.connect(self._mark_testing_controls_dirty)
        save_testing = QPushButton("Save Testing Mode")
        save_testing.clicked.connect(self.save_testing_mode)
        testing_form.addRow(self.testing_mode)
        testing_form.addRow("Daily testing limit", self.testing_limit)
        testing_form.addRow(save_testing)
        testing_note = QLabel(
            "Testing mode sirf simulated paper capture ko unlock karta hai. Target, stop-loss, time-exit, "
            "event/data-quality checks aur open-position monitoring hamesha active rahenge."
        )
        testing_note.setWordWrap(True)
        testing_form.addRow(testing_note)
        layout.addWidget(testing_box)

        cards = QGridLayout()
        self.status = self._card("Today's guard")
        self.limit = self._card("Paper trades today")
        self.streak = self._card("Consecutive losses")
        self.validation = self._card("Paper validation")
        for index, card in enumerate((self.status, self.limit, self.streak, self.validation)):
            card[0].setMinimumHeight(105 if card is not self.validation else 145)
            cards.addWidget(card[0], index // 2, index % 2)
        layout.addLayout(cards)

        check_box = QGroupBox("Daily Recovery check-in")
        check_box.setMinimumHeight(190)
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
            "• Testing Mode: selected limit tak maximum 20 simulated trades/day; target/stop/time exits active.\n"
            "• 2 consecutive paper losses: 48-hour cooling lock.\n"
            "• STRESSED, ANGRY, FOMO or REVENGE state: new captures paused for the day.\n"
            "• At least 30 separate paper sessions are required before real-money eligibility can even be reviewed.\n"
            "• Testing Mode sirf behavioural/recovery frequency guard suspend karta hai; event, stale-data, "
            "liquidity, expiry, open-position, target, stop-loss aur time-exit safety active rehti hai."
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
        settings = SettingsStore().load()
        database = Database()
        try:
            assessment = self.guard.assess(settings, database)
            progress = database.paper_trade_progress()
        finally:
            database.close()
        if not self.testing_controls_dirty:
            self.testing_mode.blockSignals(True)
            self.testing_limit.blockSignals(True)
            self.testing_mode.setChecked(bool(settings.get("paper_validation_testing_mode", False)))
            self.testing_limit.setValue(int(settings.get("paper_validation_daily_limit", 20)))
            self.testing_mode.blockSignals(False)
            self.testing_limit.blockSignals(False)
        mode = assessment.get("mode", "RECOVERY PROTECTION")
        self.status[1].setText(f"{mode}\nREADY — PAPER ONLY" if assessment["allowed"] else f"{mode}\nLOCKED\n" + "\n".join(assessment["blockers"]))
        self.limit[1].setText(f"{assessment.get('paper_trades_today', 0)} / {assessment.get('daily_limit', 1)}")
        self.streak[1].setText(str(assessment.get("loss_streak", 0)))
        self.validation[1].setText(
            f"{assessment.get('paper_sessions', 0)} / {assessment.get('paper_session_target', 30)} sessions\n"
            f"Captured {progress.get('trades', 0)} | Closed {progress.get('closed_trades', 0)} | Open {progress.get('open_trades', 0)}\n"
            f"Target {progress.get('target_hits', 0)} | Stop {progress.get('stoploss_hits', 0)} | Time exit {progress.get('time_exits', 0)}\n"
            f"Target-vs-stop accuracy {progress.get('target_vs_stop_accuracy', 0):.1f}% | Closed P&L win rate {progress.get('closed_trade_win_rate', 0):.1f}%"
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

    def save_testing_mode(self):
        settings = SettingsStore().load()
        settings["paper_validation_testing_mode"] = self.testing_mode.isChecked()
        settings["paper_validation_daily_limit"] = self.testing_limit.value()
        try:
            SettingsStore().save(settings)
        except ValueError as error:
            QMessageBox.warning(self, "Paper validation mode", str(error))
            return
        self.testing_controls_dirty = False
        self.refresh()
        if self.testing_mode.isChecked():
            QMessageBox.information(
                self, "Paper validation mode",
                f"Testing mode ON. Cutie maximum {self.testing_limit.value()} simulated trades/day allow karegi; "
                "target, stop-loss aur time-exit monitoring active rahega."
            )
        else:
            QMessageBox.information(self, "Paper validation mode", "Testing mode OFF. Recovery/overtrading protection dobara active hai.")

    def _mark_testing_controls_dirty(self, *_args):
        """Do not let periodic status refresh overwrite an unsaved testing choice."""
        self.testing_controls_dirty = True
