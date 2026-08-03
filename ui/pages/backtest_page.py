from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from engine.backtest_engine import run_tps_backtest
from engine.live_setup_capture import INSTRUMENTS, TIMEFRAMES
from services.live_session import LiveSession


class BacktestPage(QWidget):
    """Historical, paper-only validation page for TPS candle rules."""
    result_ready = Signal(dict)
    run_error = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Historical Backtesting — candle-based TPS rule validation (paper simulation only)"))
        note = QLabel(
            "Tests index candles using EMA 5/20/50, VWAP where volume is available, SuperTrend, RSI 14 and ATR 14. "
            "Results exclude option premiums, slippage, brokerage, taxes and future performance."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.timeframe = QComboBox(); self.timeframe.addItems(("5m", "15m", "1h", "1D"))
        self.days = QComboBox(); self.days.addItems(("5", "15", "30", "60", "365"))
        form.addRow("Underlying", self.symbol)
        form.addRow("Timeframe", self.timeframe)
        form.addRow("History days", self.days)
        layout.addLayout(form)
        self.run_button = QPushButton("Run Historical Backtest")
        self.run_button.clicked.connect(self.run_backtest)
        layout.addWidget(self.run_button)
        self.summary = QLabel("Connect Angel One, select a symbol and run a paper backtest.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self.result_ready.connect(self.show_result)
        self.run_error.connect(self.show_error)

    def run_backtest(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect read-only live data from Settings before downloading candle history.")
            return
        self.run_button.setEnabled(False)
        self.summary.setText("Downloading historical candles and running paper simulation…")
        Thread(target=self._run_backtest, args=(self.symbol.currentText(), self.timeframe.currentText(), int(self.days.currentText())), daemon=True).start()

    def _run_backtest(self, symbol, timeframe, days):
        try:
            exchange, token = INSTRUMENTS[symbol]
            interval = TIMEFRAMES[timeframe][0]
            candles = LiveSession.client.get_recent_candles(exchange, token, interval, days)
            result = run_tps_backtest(candles)
            result.update({"symbol": symbol, "timeframe": timeframe, "days": days, "candles": len(candles)})
            self.result_ready.emit(result)
        except (RuntimeError, ValueError) as error:
            self.run_error.emit(str(error))

    def show_result(self, result):
        self.run_button.setEnabled(True)
        volume_note = "Volume confirmation applied." if result["volume_available"] else "Index volume unavailable: volume condition was kept neutral."
        self.summary.setText(
            f"{result['symbol']} {result['timeframe']} | {result['candles']} candles / {result['days']} days\n"
            f"Paper trades: {result['total_trades']} | Wins: {result['wins']} | Losses: {result['losses']} | "
            f"Win rate: {result['win_rate']:.1f}%\nNet points: {result['net_points']:,.2f} | "
            f"Max drawdown: {result['max_drawdown_points']:,.2f}\n{volume_note}\n"
            "Use this to compare rule versions; it is not a promise of live profit."
        )
        headers = ["Time", "Direction", "Entry", "Stop", "Target", "Exit", "Outcome", "P&L Points", "RSI 14", "ATR 14"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(result["trades"]))
        for row, trade in enumerate(result["trades"]):
            values = (trade["time"], trade["direction"], trade["entry"], trade["stoploss"], trade["target"], trade["exit"],
                      trade["outcome"], trade["pnl_points"], trade["rsi_14"], trade["atr_14"])
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def show_error(self, message):
        self.run_button.setEnabled(True)
        self.summary.setText(f"Backtest unavailable: {message}")
