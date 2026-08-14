import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.pages.options_page import OptionsPage, SessionComboBox, SessionSpinBox


class OptionsSessionControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_app_data = patch.dict(os.environ, {"LOCALAPPDATA": self.temp_dir.name})
        self.local_app_data.start()
        self.page = OptionsPage()

    def tearDown(self):
        self.page.db.connection.close()
        self.page.close()
        self.local_app_data.stop()
        self.temp_dir.cleanup()

    def test_event_and_testing_controls_belong_to_session_checklist(self):
        session_controls = (
            self.page.event_check,
            self.page.news_pause,
            self.page.event_override,
            self.page.event_window,
            self.page.minimum_score,
            self.page.match_mode,
            self.page.required_matches,
        )
        for control in session_controls:
            self.assertTrue(self.page.session_checklist_group.isAncestorOf(control))
            self.assertFalse(self.page.contract_group.isAncestorOf(control))

    def test_session_fields_ignore_mouse_wheel_changes(self):
        for control in (
            self.page.required_matches,
            self.page.minimum_score,
            self.page.match_mode,
            self.page.event_check,
            self.page.event_window,
        ):
            event = Mock()
            before = control.currentIndex() if isinstance(control, SessionComboBox) else control.value()
            control.wheelEvent(event)
            after = control.currentIndex() if isinstance(control, SessionComboBox) else control.value()
            event.ignore.assert_called_once_with()
            self.assertEqual(after, before)

        self.assertIsInstance(self.page.required_matches, SessionSpinBox)
        self.assertIsInstance(self.page.minimum_score, SessionSpinBox)

    def test_save_receipt_includes_threshold_and_event_safety(self):
        self.page.show_session_save_confirmation()
        receipt = self.page.checklist_save_status.text()
        self.assertIn("Testing score:", receipt)
        self.assertIn("Event:", receipt)
        self.assertIn("Window:", receipt)
        self.assertIn("Pause:", receipt)
        self.assertIn("Override:", receipt)


if __name__ == "__main__":
    unittest.main()
