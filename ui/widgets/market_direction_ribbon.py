from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from core.database_manager import Database
from services.market_direction_ribbon_service import build_market_direction_ribbon


class MarketDirectionRibbon(QFrame):
    """Persistent full-width direction ribbon backed by saved market evidence."""

    COLORS = {"BULLISH": "#35d07f", "BEARISH": "#ff647c", "FLAT": "#ffd166", "DATA GAP": "#aab2c8"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("marketDirectionRibbon")
        self.setFixedHeight(34)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        self.label = QLabel("TPS MARKET DIRECTION  |  Waiting for completed 5-minute evidence")
        self.label.setObjectName("marketDirectionRibbonLabel")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumWidth(0)
        layout.addWidget(self.label, 1)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        database = Database()
        try:
            result = build_market_direction_ribbon(database)
        finally:
            database.close()
        index_text = "  |  ".join(f"{row['symbol']} {row['direction']}" for row in result["indexes"])
        self.label.setText(
            f"TPS MARKET {result['overall']}  |  {index_text}  |  "
            f"CANDLE {result['evidence_time']}  |  {result['session']}"
        )
        color = self.COLORS.get(result["overall"], self.COLORS["DATA GAP"])
        self.label.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.setToolTip("Chart + quality-gated OI + component breadth verdict. DATA GAP ko direction nahi maana jata.")
