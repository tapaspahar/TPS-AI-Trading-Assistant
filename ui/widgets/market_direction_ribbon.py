from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QLabel

from core.database_manager import Database
from services.market_direction_ribbon_service import build_market_direction_ribbon


def format_market_direction_text(result):
    index_text = "  |  ".join(f"{row['symbol']} : {row['direction']}" for row in result["indexes"])
    return (
        f"TPS MARKET : {result['overall']}  |  {index_text}  |  "
        f"CANDLE : {result['evidence_time']}  |  {result['session']}"
    )


class MarketDirectionRibbon(QFrame):
    """Persistent full-width direction ribbon backed by saved market evidence."""

    COLORS = {"BULLISH": "#35d07f", "BEARISH": "#ff647c", "FLAT": "#ffd166", "DATA GAP": "#aab2c8"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("marketDirectionRibbon")
        self.setFixedHeight(34)
        self.label = QLabel("TPS MARKET DIRECTION  |  Waiting for completed 5-minute evidence")
        self.label.setParent(self)
        self.label.setObjectName("marketDirectionRibbonLabel")
        self.label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.label.adjustSize()
        self._ticker_x = 0
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(30)
        self.scroll_timer.timeout.connect(self._scroll_once)
        self.scroll_timer.start()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        QTimer.singleShot(0, self.refresh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ticker_x <= 0:
            self._ticker_x = self.width()
            self.label.move(self._ticker_x, 0)

    def _scroll_once(self):
        if self.width() <= 0:
            return
        self._ticker_x -= 2
        if self._ticker_x + self.label.width() < 0:
            self._ticker_x = self.width()
        self.label.move(self._ticker_x, 0)

    def refresh(self):
        database = Database()
        try:
            result = build_market_direction_ribbon(database)
        finally:
            database.close()
        updated = format_market_direction_text(result)
        if updated != self.label.text():
            self.label.setText(updated)
            self.label.adjustSize()
            self.label.setFixedHeight(self.height())
        color = self.COLORS.get(result["overall"], self.COLORS["DATA GAP"])
        self.label.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.label.adjustSize()
        self.label.setFixedHeight(self.height())
        self.setToolTip("Chart + quality-gated OI + component breadth verdict. DATA GAP ko direction nahi maana jata.")
