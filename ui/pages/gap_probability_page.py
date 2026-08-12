from __future__ import annotations

from datetime import date, datetime, time, timedelta
from threading import Thread

from PySide6.QtCore import Signal
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


class GapProbabilityPage(QWidget):
    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.live_values = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(16, 14, 16, 18); layout.setSpacing(10)
        scroll.setWidget(content); outer.addWidget(scroll)

        title = QLabel("3:20 Gap Probability Lab"); title.setObjectName("pageTitle"); layout.addWidget(title)
        note = QLabel(
            "At or after 3:20 PM, TPS combines completed Spot/Future trend, futures basis, OI-PCR and the latest available official FII/DII cash flow into Gap Up, Flat and Gap Down probabilities. This is a measured forecast—not a guarantee—and overnight news remains unknowable at 3:20 PM."
        )
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.load_button = QPushButton("Load Live 3:20 Evidence")
        self.load_button.clicked.connect(self.load_live)
        controls.addWidget(QLabel("Index"), 0, 0); controls.addWidget(self.symbol, 0, 1); controls.addWidget(self.load_button, 0, 2)
        layout.addLayout(controls)
        self.status = QLabel("Connect broker data first. Before 3:20 PM the saved output is clearly marked PREVIEW.")
        self.status.setWordWrap(True); layout.addWidget(self.status)

        institution = QGroupBox("Latest available official institutional cash activity (optional, ₹ crore)")
        form = QFormLayout(institution)
        self.flow_date = QLineEdit(); self.flow_date.setPlaceholderText("YYYY-MM-DD")
        self.fii = QLineEdit(); self.fii.setPlaceholderText("Example: -2350.50")
        self.dii = QLineEdit(); self.dii.setPlaceholderText("Example: 1800.25")
        form.addRow("Published data date", self.flow_date); form.addRow("FII/FPI cash net", self.fii); form.addRow("DII cash net", self.dii)
        flow_note = QLabel("3:20 PM par same-day final FII/DII cash totals aam taur par complete nahi hote. Latest published NSE FII/FPI & DII report value use karein; blank chhodne par TPS koi value guess nahi karega.")
        flow_note.setWordWrap(True); form.addRow(flow_note)
        layout.addWidget(institution)

        self.calculate_button = QPushButton("Calculate and Save Gap Probability")
        self.calculate_button.clicked.connect(self.calculate); self.calculate_button.setEnabled(False)
        layout.addWidget(self.calculate_button)
        cards = QGridLayout(); self.cards = {
            "up": DashboardCard("Gap Up", "-"), "flat": DashboardCard("Flat / Inside", "-"),
            "down": DashboardCard("Gap Down", "-"), "quality": DashboardCard("Model confidence", "-"),
        }
        for column, card in enumerate(self.cards.values()):
            card.set_compact(True); card.setMinimumHeight(92); cards.addWidget(card, 0, column)
        layout.addLayout(cards)
        self.explanation = QLabel("No probability generated yet."); self.explanation.setWordWrap(True); layout.addWidget(self.explanation)

        history_box = QGroupBox("Forecast verification history")
        history_layout = QVBoxLayout(history_box)
        self.metrics = QLabel("Verified samples: 0 | Accuracy: waiting for next-session opens")
        history_layout.addWidget(self.metrics)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(("Forecast", "Target", "Index", "Stage", "Prediction", "Up", "Flat", "Down", "Actual / Result"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.setMinimumHeight(250)
        history_layout.addWidget(self.table); layout.addWidget(history_box)
        layout.addStretch()
        self.loaded.connect(self._apply_live); self.failed.connect(self._show_error)
        self.refresh_history()

    def load_live(self):
        if not LiveSession.connected():
            self.status.setText("Broker live data is not connected. Settings se live data connect kijiye."); return
        self.load_button.setEnabled(False); self.calculate_button.setEnabled(False)
        symbol = self.symbol.currentText(); self.status.setText(f"Loading completed {symbol} Spot, Future and OI evidence...")
        Thread(target=self._load_worker, args=(symbol,), daemon=True).start()

    def _load_worker(self, symbol):
        try:
            self.loaded.emit(NextDayBiasDataService(LiveSession.client).load(symbol))
        except (RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
            self.failed.emit(str(error))

    def _apply_live(self, data):
        self.load_button.setEnabled(True); self.calculate_button.setEnabled(True); self.live_values = data
        stage = self._stage()
        self.status.setText(
            f"{data['symbol']} evidence ready | Spot candle {data['spot_candle_time']} | Future {data['future_symbol']} | "
            f"OI-PCR {float(data.get('oi_pcr') or 0):.2f} | Save stage: {stage}."
        )

    def _show_error(self, message):
        self.load_button.setEnabled(True); self.calculate_button.setEnabled(False); self.live_values = None
        self.status.setText(f"Gap evidence unavailable: {message}")

    def calculate(self):
        if not self.live_values:
            return
        try:
            if self.flow_date.text().strip():
                datetime.strptime(self.flow_date.text().strip(), "%Y-%m-%d")
            data = self.live_values
            values = {
                **{f"spot_{key}": data["spot"].get(source) for key, source in (("close", "close"), ("ema5", "ema_5"), ("ema20", "ema_20"), ("ema50", "ema_50"), ("vwap", "vwap"), ("supertrend", "supertrend"))},
                **{f"future_{key}": data["future"].get(source) for key, source in (("close", "close"), ("ema5", "ema_5"), ("ema20", "ema_20"), ("ema50", "ema_50"), ("vwap", "vwap"), ("supertrend", "supertrend"))},
                "oi_pcr": data.get("oi_pcr"), "fii_net": self.fii.text().strip(), "dii_net": self.dii.text().strip(),
                "institutional_date": self.flow_date.text().strip(),
            }
            result = GapProbabilityEngine().analyze(values)
            today = date.today(); target = self._next_weekday(today)
            forecast = {
                **result, "forecast_date": today.isoformat(), "target_date": target.isoformat(),
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "symbol": data["symbol"], "stage": self._stage(), "prior_close": float(data["spot"]["close"]),
                "inputs": values,
            }
            database = Database(); database.save_gap_probability_forecast(forecast); database.close()
            self.cards["up"].set_value(f"{result['gap_up_probability']:.1f}%")
            self.cards["flat"].set_value(f"{result['flat_probability']:.1f}%")
            self.cards["down"].set_value(f"{result['gap_down_probability']:.1f}%")
            self.cards["quality"].set_value(f"{result['confidence']}% confidence\n{result['data_quality']}% data quality")
            evidence = "\n• ".join(result["evidence"])
            self.explanation.setText(
                f"{data['symbol']} target session {target.strftime('%d-%m-%Y')} | Highest probability: {result['predicted_class']}\n"
                f"Evidence:\n• {evidence}\n\nActual classification uses ±{result['gap_threshold_percent']:.2f}% versus this close. "
                "Overnight global markets, GIFT NIFTY, currency, crude and unexpected news can reverse this result."
            )
            self.refresh_history()
        except (ValueError, TypeError, KeyError) as error:
            self.status.setText(f"Input error: {error}")

    def refresh_history(self):
        database = Database(); database.resolve_gap_probability_outcomes()
        rows = database.get_gap_probability_forecasts(limit=100); database.close()
        verified = [row for row in rows if row["correct"] is not None]
        accuracy = sum(int(row["correct"]) for row in verified) / len(verified) * 100 if verified else 0
        self.metrics.setText(
            f"Verified samples: {len(verified)} | Accuracy: {accuracy:.1f}%" if verified
            else "Verified samples: 0 | Accuracy will appear after the next saved 5-minute session open"
        )
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            actual = "Pending"
            if row["actual_class"]:
                actual = f"{row['actual_class']} {float(row['actual_gap_percent']):+.2f}% | {'CORRECT' if row['correct'] else 'MISS'}"
            values = (row["forecast_date"], row["target_date"], row["symbol"], row["stage"], row["predicted_class"],
                      f"{row['gap_up_probability']:.1f}%", f"{row['flat_probability']:.1f}%", f"{row['gap_down_probability']:.1f}%", actual)
            for column, value in enumerate(values):
                self.table.setItem(r, column, QTableWidgetItem(str(value)))

    @staticmethod
    def _stage():
        return "3:20 FINAL" if datetime.now().time() >= time(15, 20) else "PREVIEW"

    @staticmethod
    def _next_weekday(day):
        candidate = day + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate
