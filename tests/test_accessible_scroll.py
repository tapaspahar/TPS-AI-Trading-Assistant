import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from ui.widgets.accessible_scroll import ArrowScrollBar, configure_scroll_area


class AccessibleScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.area = QScrollArea()
        content = QWidget()
        content.setMinimumHeight(1200)
        self.area.setWidget(content)
        self.area.resize(400, 300)
        self.bar = configure_scroll_area(self.area)
        self.area.show()
        self.app.processEvents()

    def tearDown(self):
        self.area.close()

    def test_arrow_buttons_move_scrollbar_up_and_down(self):
        self.assertIsInstance(self.bar, ArrowScrollBar)
        self.bar.setValue(200)
        QTest.mouseClick(self.bar, Qt.LeftButton, pos=QPoint(self.bar.width() // 2, 3))
        self.assertLess(self.bar.value(), 200)
        current = self.bar.value()
        QTest.mouseClick(
            self.bar, Qt.LeftButton,
            pos=QPoint(self.bar.width() // 2, self.bar.height() - 3),
        )
        self.assertGreater(self.bar.value(), current)

    def test_mouse_wheel_moves_page_in_both_directions(self):
        self.bar.setValue(200)
        down = QWheelEvent(
            QPointF(5, 100), QPointF(5, 100), QPoint(), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )
        QApplication.sendEvent(self.area.viewport(), down)
        self.assertEqual(self.bar.value(), 200 + ArrowScrollBar.WHEEL_STEP)
        up = QWheelEvent(
            QPointF(5, 100), QPointF(5, 100), QPoint(), QPoint(0, 120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )
        QApplication.sendEvent(self.area.viewport(), up)
        self.assertEqual(self.bar.value(), 200)


if __name__ == "__main__":
    unittest.main()
