from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, Signal


class DashboardCard(QFrame):

    clicked = Signal()

    def __init__(self, title, value):

        super().__init__()

        self.setObjectName("dashboardCard")
        self.compact = False
        self._clickable = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)

        titleLabel = QLabel(title)
        titleLabel.setObjectName("cardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")

        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setWordWrap(True)

        layout.addWidget(titleLabel)
        layout.addStretch()
        layout.addWidget(self.value_label)

    def set_clickable(self, enabled=True, tooltip=""):
        """Make a summary card behave like an accessible navigation control."""
        self._clickable = bool(enabled)
        self.setCursor(Qt.PointingHandCursor if self._clickable else Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus if self._clickable else Qt.NoFocus)
        self.setProperty("clickable", self._clickable)
        if tooltip:
            self.setToolTip(str(tooltip))
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._clickable and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_value(self, value):
        text = str(value)
        self.value_label.setText(text)
        density = "compact" if self.compact or len(text) > 20 or "\n" in text else "normal"
        self.value_label.setProperty("density", density)
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)

    def set_compact(self, enabled=True):
        self.compact = enabled
        if enabled:
            self.setFixedHeight(76)
            # A compact market card can still contain price + one signal line.
            self.value_label.setMinimumHeight(34)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.value_label.setMinimumHeight(0)
        self.set_value(self.value_label.text())
