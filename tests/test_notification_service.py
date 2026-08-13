import json
import tempfile
import unittest
from pathlib import Path

from core.settings_store import SettingsStore
from datetime import datetime, timezone

from services.notification_service import category_enabled, daily_event_key


class NotificationSettingsTests(unittest.TestCase):
    def test_defaults_keep_important_trade_alerts_on(self):
        with tempfile.TemporaryDirectory() as folder:
            values = SettingsStore(Path(folder) / "settings.json").load()
        self.assertTrue(category_enabled(values, "trade_capture"))
        self.assertTrue(category_enabled(values, "target_achieved"))
        self.assertFalse(category_enabled(values, "auto_attempt_report"))

    def test_saved_partial_preferences_are_merged_with_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"notification_preferences": {"trade_capture": False}}), encoding="utf-8")
            values = SettingsStore(path).load()
        self.assertFalse(category_enabled(values, "trade_capture"))
        self.assertTrue(category_enabled(values, "target_achieved"))

    def test_global_switch_disables_every_category(self):
        settings = {"notifications_enabled": False, "notification_preferences": {"trade_capture": True}}
        self.assertFalse(category_enabled(settings, "trade_capture"))

    def test_daily_event_key_ignores_changing_tick_message(self):
        now = datetime(2026, 8, 13, 10, 15, tzinfo=timezone.utc)
        first = daily_event_key("support_resistance", "SENSEX:support:78000", now)
        second = daily_event_key("support_resistance", "SENSEX:support:78000", now)
        other_level = daily_event_key("support_resistance", "SENSEX:support:78100", now)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other_level)


if __name__ == "__main__":
    unittest.main()
