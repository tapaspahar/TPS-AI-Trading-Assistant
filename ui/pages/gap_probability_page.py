from __future__ import annotations

from datetime import date, datetime, time, timedelta
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QGroupBox, QHeaderView, QLabel,
    QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.database_manager import Database
from engine.gap_probability_engine import GapProbabilityEngine
from services.live_session import LiveSession
from services.next_day_bias_data_service import NextDayBiasDataService
from ui.widgets.cards.dashboard_card import DashboardCard
from ui.widgets.excel_export_dialog import open_excel_export


ACTIONABLE_STAGE = "3:20 ACTIONABLE"
CLOSE_STAGE = "3:40 CLOSE CONFIRMATION"


class GapProbabilityPage(QWidget):
    """Separate 3:20 decision snapshot and 3:40 closing confirmation."""

    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.live_values = None
        self.db = Database()
        self._requested_stage = None
        self._load_in_progress = False
        self._last_auto_attempt = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 18)
        layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        title = QLabel("3:20 + 3:40 Gap Probability Lab")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel(
            "TPS publishes two separate next-session forecasts: a 3:20 PM actionable snapshot and a "
            "3:40 PM post-close confirmation. Both combine completed Spot/Future trend, futures basis, "
            "OI-PCR and optional official FII/DII cash flow. The 3:40 result confirms or challenges the "
            "3:20 view; neither is a guaranteed gap or financial advice."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        controls = QGridLayout()
        self.symbol = QComboBox()
        self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.load_button = QPushButton("Load Current Evidence")
        self.load_button.clicked.connect(self.load_live)
        controls.addWidget(QLabel("Index"), 0, 0)
        controls.addWidget(self.symbol, 0, 1)
        controls.addWidget(self.load_button, 0, 2)
        excel = QPushButton("Export Excel by Date / Period")
        excel.clicked.connect(lambda: open_excel_export(self, self.db, "gap_probability"))
        controls.addWidget(excel, 0, 3)
        layout.addLayout(controls)
        self.status = QLabel(
            "Connect broker data first. TPS auto-captures the selected index near 3:20 PM and again "
            "at/after 3:40 PM while the application is open."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        institution = QGroupBox("Latest available official institutional cash activity (optional, Rs crore)")
        form = QFormLayout(institution)
        self.flow_date = QLineEdit()
        self.flow_date.setPlaceholderText("YYYY-MM-DD")
        self.fii = QLineEdit()
        self.fii.setPlaceholderText("Example: -2350.50")
        self.dii = QLineEdit()
        self.dii.setPlaceholderText("Example: 1800.25")
        form.addRow("Published data date", self.flow_date)
        form.addRow("FII/FPI cash net", self.fii)
        form.addRow("DII cash net", self.dii)
        flow_note = QLabel(
            "Same-day final FII/DII totals may still be unavailable. Latest published official values use "
            "karein; blank chhodne par TPS koi value guess nahi karega."
        )
        flow_note.setWordWrap(True)
        form.addRow(flow_note)
        layout.addWidget(institution)

        self.calculate_button = QPushButton("Calculate and Save Current Stage")
        self.calculate_button.clicked.connect(self.calculate)
        self.calculate_button.setEnabled(False)
        layout.addWidget(self.calculate_button)

        self.stage_cards = {}
        self.stage_summaries = {}
        layout.addWidget(self._stage_panel(ACTIONABLE_STAGE, "3:20 PM actionable forecast (manual overnight decision-support)"))
        layout.addWidget(self._stage_panel(CLOSE_STAGE, "3:40 PM closing confirmation (post-close recalculation)"))
        # Kept for compatibility with code/tests that referred to the original card group.
        self.cards = self.stage_cards[ACTIONABLE_STAGE]
        self.explanation = QLabel("No 3:20 or 3:40 probability generated yet.")
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)

        history_box = QGroupBox("Forecast verification history")
        history_layout = QVBoxLayout(history_box)
        self.metrics = QLabel("Verified samples: 0 | Accuracy: waiting for next-session opens")
        history_layout.addWidget(self.metrics)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ("Forecast", "Target", "Index", "Stage", "Prediction", "Up", "Flat", "Down", "Actual / Result")
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(250)
        history_layout.addWidget(self.table)
        layout.addWidget(history_box)
        layout.addStretch()

        self.loaded.connect(self._apply_live)
        self.failed.connect(self._show_error)
        self.symbol.currentTextChanged.connect(lambda _value: self._refresh_stage_results())
        self.refresh_history()
        self._refresh_stage_results()
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(30_000)
        self.auto_timer.timeout.connect(self._run_scheduled_capture)
        self.auto_timer.start()
        QTimer.singleShot(2_000, self._run_scheduled_capture)

    def _stage_panel(self, stage, title):
        box = QGroupBox(title)
        panel = QVBoxLayout(box)
        grid = QGridLayout()
        cards = {
            "up": DashboardCard("Gap Up", "-"),
            "flat": DashboardCard("Flat / Inside", "-"),
            "down": DashboardCard("Gap Down", "-"),
            "quality": DashboardCard("Model confidence", "-"),
        }
        for column, card in enumerate(cards.values()):
            card.set_compact(True)
            card.setMinimumHeight(82)
            grid.addWidget(card, 0, column)
        summary = QLabel("Not captured yet.")
        summary.setWordWrap(True)
        panel.addLayout(grid)
        panel.addWidget(summary)
        self.stage_cards[stage] = cards
        self.stage_summaries[stage] = summary
        return box

    def load_live(self, _checked=False, requested_stage=None):
        if self._load_in_progress:
            return
        if not LiveSession.connected():
            self.status.setText("Broker live data is not connected. Settings se live data connect kijiye.")
            return
        self._load_in_progress = True
        self._requested_stage = requested_stage
        self.load_button.setEnabled(False)
        self.calculate_button.setEnabled(False)
        symbol = self.symbol.currentText()
        self.status.setText(f"Loading completed {symbol} Spot, Future and OI evidence...")
        Thread(target=self._load_worker, args=(symbol,), daemon=True).start()

    def _load_worker(self, symbol):
        try:
            self.loaded.emit(NextDayBiasDataService(LiveSession.client).load(symbol))
        except (RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
            self.failed.emit(str(error))

    def _apply_live(self, data):
        self._load_in_progress = False
        self.load_button.setEnabled(True)
        self.calculate_button.setEnabled(True)
        self.live_values = data
        stage = self._requested_stage or self._stage()
        self.status.setText(
            f"{data['symbol']} evidence ready | Spot candle {data['spot_candle_time']} | "
            f"Future {data['future_symbol']} | OI-PCR {float(data.get('oi_pcr') or 0):.2f} | Save stage: {stage}."
        )
        if self._requested_stage:
            requested = self._requested_stage
            self._requested_stage = None
            if not self._is_current_session_candle(data.get("spot_candle_time")):
                self.live_values = None
                self.calculate_button.setEnabled(False)
                self.status.setText(
                    f"Automatic {requested} not saved: broker returned an older-session candle "
                    f"({data.get('spot_candle_time') or 'time unavailable'})."
                )
                return
            self._calculate_and_save(requested, automatic=True)

    def _show_error(self, message):
        requested = self._requested_stage
        self._requested_stage = None
        self._load_in_progress = False
        self.load_button.setEnabled(True)
        self.calculate_button.setEnabled(False)
        self.live_values = None
        prefix = f"Automatic {requested} capture failed. " if requested else ""
        self.status.setText(f"{prefix}Gap evidence unavailable: {message}")

    def calculate(self, _checked=False):
        self._calculate_and_save(self._stage(), automatic=False)

    def _calculate_and_save(self, stage, automatic=False):
        if not self.live_values:
            return
        try:
            if self.flow_date.text().strip():
                datetime.strptime(self.flow_date.text().strip(), "%Y-%m-%d")
            data = self.live_values
            values = {
                **{f"spot_{key}": data["spot"].get(source) for key, source in (
                    ("close", "close"), ("ema5", "ema_5"), ("ema20", "ema_20"),
                    ("ema50", "ema_50"), ("vwap", "vwap"), ("supertrend", "supertrend"),
                )},
                **{f"future_{key}": data["future"].get(source) for key, source in (
                    ("close", "close"), ("ema5", "ema_5"), ("ema20", "ema_20"),
                    ("ema50", "ema_50"), ("vwap", "vwap"), ("supertrend", "supertrend"),
                )},
                "oi_pcr": data.get("oi_pcr"),
                "fii_net": self.fii.text().strip(),
                "dii_net": self.dii.text().strip(),
                "institutional_date": self.flow_date.text().strip(),
            }
            result = GapProbabilityEngine().analyze(values)
            today = date.today()
            target = self._next_weekday(today)
            forecast = {
                **result,
                "forecast_date": today.isoformat(),
                "target_date": target.isoformat(),
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "symbol": data["symbol"],
                "stage": stage,
                "prior_close": float(data["spot"]["close"]),
                "inputs": values,
            }
            database = Database()
            database.save_gap_probability_forecast(forecast)
            database.close()
            evidence = " | ".join(result["evidence"])
            display_stage = stage if stage in self.stage_summaries else ACTIONABLE_STAGE
            cards = self.stage_cards[display_stage]
            cards["up"].set_value(f"{result['gap_up_probability']:.1f}%")
            cards["flat"].set_value(f"{result['flat_probability']:.1f}%")
            cards["down"].set_value(f"{result['gap_down_probability']:.1f}%")
            cards["quality"].set_value(f"{result['confidence']}% confidence\n{result['data_quality']}% data quality")
            self.stage_summaries[display_stage].setText(
                f"Saved {datetime.now().strftime('%H:%M:%S')} | {result['predicted_class']} | "
                f"Target {target.strftime('%d-%m-%Y')} | {'Automatic' if automatic else 'Manual'} capture | {evidence}"
            )
            self.refresh_history()
            if stage == "PREVIEW":
                self.explanation.setText(
                    f"PREVIEW ONLY: {result['predicted_class']} | This is not the protected 3:20 snapshot. "
                    "TPS will recalculate from completed evidence during the 3:20 capture window."
                )
            else:
                self._refresh_stage_results()
            suffix = (
                "It will not replace either protected stage."
                if stage == "PREVIEW" else "Both protected stages remain separate for comparison."
            )
            self.status.setText(f"{stage} saved for {data['symbol']}. {suffix}")
        except (ValueError, TypeError, KeyError) as error:
            self.status.setText(f"Input error: {error}")

    def _run_scheduled_capture(self):
        if self._load_in_progress or not LiveSession.connected():
            return
        now = datetime.now().astimezone()
        if now.weekday() >= 5:
            return
        stage = self._automatic_stage_due(now.time())
        if not stage:
            return
        previous_attempt = self._last_auto_attempt.get(stage)
        if previous_attempt and (now - previous_attempt).total_seconds() < 300:
            return
        database = Database()
        existing = database.get_gap_probability_forecasts(self.symbol.currentText(), limit=20)
        database.close()
        already_saved = any(
            row["forecast_date"] == now.date().isoformat() and row["stage"] == stage
            for row in existing
        )
        if not already_saved:
            self._last_auto_attempt[stage] = now
            self.status.setText(f"Automatic {stage} capture is due; loading completed market evidence...")
            self.load_live(requested_stage=stage)

    def _refresh_stage_results(self):
        database = Database()
        rows = database.get_gap_probability_forecasts(self.symbol.currentText(), limit=100)
        database.close()
        today = date.today().isoformat()
        latest = {row["stage"]: row for row in rows if row["forecast_date"] == today}
        for stage in (ACTIONABLE_STAGE, CLOSE_STAGE):
            row = latest.get(stage)
            cards = self.stage_cards[stage]
            if not row:
                for card in cards.values():
                    card.set_value("-")
                self.stage_summaries[stage].setText("Not captured yet.")
                continue
            cards["up"].set_value(f"{row['gap_up_probability']:.1f}%")
            cards["flat"].set_value(f"{row['flat_probability']:.1f}%")
            cards["down"].set_value(f"{row['gap_down_probability']:.1f}%")
            cards["quality"].set_value(f"{row['confidence']}% confidence\n{row['data_quality']}% data quality")
            captured = str(row["generated_at"])[11:19]
            self.stage_summaries[stage].setText(
                f"Captured {captured} | Highest probability: {row['predicted_class']} | "
                f"Prior close {float(row['prior_close']):,.2f}"
            )
        action = latest.get(ACTIONABLE_STAGE)
        close = latest.get(CLOSE_STAGE)
        if action and close:
            label = "CONFIRMED" if action["predicted_class"] == close["predicted_class"] else "CHANGED"
            self.explanation.setText(
                f"Closing check: {label} | 3:20 {action['predicted_class']} -> 3:40 {close['predicted_class']}. "
                "3:20 can support a discretionary manual overnight decision, but 3:40 is the stronger closing "
                "confirmation. Overnight global markets, GIFT NIFTY, currency, crude and unexpected news can "
                "still reverse either forecast."
            )
        elif action:
            self.explanation.setText(
                f"3:20 view: {action['predicted_class']} | Awaiting automatic 3:40 closing confirmation. "
                "Any manual overnight position remains exposed to closing and overnight change risk."
            )
        elif close:
            self.explanation.setText(
                f"3:40 closing view: {close['predicted_class']} | No separate 3:20 snapshot is available for comparison."
            )
        else:
            self.explanation.setText("No 3:20 or 3:40 probability generated yet.")

    def refresh_history(self):
        database = Database()
        database.resolve_gap_probability_outcomes()
        rows = database.get_gap_probability_forecasts(limit=100)
        database.close()
        verified = [row for row in rows if row["correct"] is not None]
        accuracy = sum(int(row["correct"]) for row in verified) / len(verified) * 100 if verified else 0
        self.metrics.setText(
            f"Verified samples: {len(verified)} | Accuracy: {accuracy:.1f}%" if verified
            else "Verified samples: 0 | Accuracy will appear after the next saved 5-minute session open"
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            actual = "Pending"
            if row["actual_class"]:
                actual = (
                    f"{row['actual_class']} {float(row['actual_gap_percent']):+.2f}% | "
                    f"{'CORRECT' if row['correct'] else 'MISS'}"
                )
            values = (
                row["forecast_date"], row["target_date"], row["symbol"], row["stage"],
                row["predicted_class"], f"{row['gap_up_probability']:.1f}%",
                f"{row['flat_probability']:.1f}%", f"{row['gap_down_probability']:.1f}%", actual,
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value)))

    @staticmethod
    def _stage(moment=None):
        current = moment or datetime.now().time()
        if current >= time(15, 40):
            return CLOSE_STAGE
        if current >= time(15, 20):
            return ACTIONABLE_STAGE
        return "PREVIEW"

    @staticmethod
    def _automatic_stage_due(current):
        if time(15, 20) <= current < time(15, 30):
            return ACTIONABLE_STAGE
        if current >= time(15, 40):
            return CLOSE_STAGE
        return None

    @staticmethod
    def _is_current_session_candle(value, today=None):
        expected = today or date.today()
        try:
            return datetime.fromisoformat(str(value)).date() == expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _next_weekday(day):
        candidate = day + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate
