"""Lightweight depth effects used by the glass UI."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect


def add_glass_shadow(widget, blur=24, y_offset=5, opacity=90):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(effect)
    return effect
