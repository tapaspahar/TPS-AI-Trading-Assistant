"""Consistent mouse-wheel and arrow-button behaviour for app scroll areas."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPolygon, QWheelEvent
from PySide6.QtWidgets import QAbstractSlider, QScrollArea, QScrollBar


class ArrowScrollBar(QScrollBar):
    """Vertical scrollbar with always-visible, clickable end arrows."""

    ARROW_AREA = 20
    WHEEL_STEP = 42

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setSingleStep(self.WHEEL_STEP)
        self.setProperty("tpsArrowScrollBar", True)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.maximum() <= self.minimum():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#7dd3fc"))
        centre = self.width() // 2
        painter.drawPolygon(QPolygon([
            QPoint(centre, 5), QPoint(centre - 5, 12), QPoint(centre + 5, 12),
        ]))
        bottom = self.height()
        painter.drawPolygon(QPolygon([
            QPoint(centre, bottom - 5),
            QPoint(centre - 5, bottom - 12),
            QPoint(centre + 5, bottom - 12),
        ]))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() > self.minimum():
            if event.position().y() <= self.ARROW_AREA:
                self.triggerAction(QAbstractSlider.SliderSingleStepSub)
                event.accept()
                return
            if event.position().y() >= self.height() - self.ARROW_AREA:
                self.triggerAction(QAbstractSlider.SliderSingleStepAdd)
                event.accept()
                return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        notches = max(1, abs(delta) // 120)
        direction = -1 if delta > 0 else 1
        self.setValue(self.value() + direction * self.WHEEL_STEP * notches)
        event.accept()


def configure_scroll_area(area: QScrollArea) -> ArrowScrollBar:
    """Install the common vertical bar without changing page content."""
    previous = area.verticalScrollBar()
    previous_value = previous.value()
    bar = ArrowScrollBar(area)
    area.setVerticalScrollBar(bar)
    bar.setValue(previous_value)
    area.setProperty("tpsWheelScrolling", True)
    return bar
