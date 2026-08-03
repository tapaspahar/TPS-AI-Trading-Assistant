import tempfile
import unittest
from pathlib import Path

from core.settings_store import SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_defaults_are_available_and_validated_values_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            self.assertEqual(store.load()["capital"], 100000.0)
            saved = store.save({"capital": "250000", "risk_percent": "0.5", "daily_loss_percent": "2", "max_trades_per_day": "3", "theme": "light"})
            self.assertEqual(saved["max_trades_per_day"], 3)
            self.assertEqual(store.load()["theme"], "light")
            self.assertEqual(store.load()["capital"], 250000.0)

    def test_invalid_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            with self.assertRaises(ValueError):
                store.save({"capital": 0, "risk_percent": 1, "daily_loss_percent": 3, "max_trades_per_day": 5})

    def test_invalid_theme_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            with self.assertRaises(ValueError):
                store.save({"capital": 100000, "risk_percent": 1, "daily_loss_percent": 3, "max_trades_per_day": 5, "theme": "blue"})
