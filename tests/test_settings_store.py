import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch

from core.settings_store import SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_legacy_local_settings_migrate_to_update_safe_roaming_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, roaming = root / "Local", root / "Roaming"
            legacy = local / "TPS AI Trading Assistant" / "settings.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({"risk_percent": 4.5, "ui_style": "maximalism"}), encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local), "APPDATA": str(roaming)}):
                store = SettingsStore()
                self.assertEqual(store.path, roaming / "TPS AI Trading Assistant" / "settings.json")
                self.assertEqual((store.load()["risk_percent"], store.load()["ui_style"]), (4.5, "maximalism"))
                self.assertTrue(store.path.exists())
                self.assertTrue(store.backup_path.exists())

    def test_atomic_save_keeps_unknown_values_and_latest_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"future_custom_setting": "KEEP", "capital": 120000}), encoding="utf-8")
            store = SettingsStore(path)
            saved = store.save({
                "capital": 120000, "risk_percent": 2, "daily_loss_percent": 4,
                "max_trades_per_day": 4,
            })
            self.assertEqual(saved["future_custom_setting"], "KEEP")
            path.write_text("broken update file", encoding="utf-8")
            recovered = store.load()
            self.assertEqual((recovered["capital"], recovered["risk_percent"]), (120000.0, 2.0))

    def test_defaults_are_available_and_validated_values_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            self.assertEqual(store.load()["capital"], 100000.0)
            self.assertEqual(store.load()["trade_plan_min_score"], 95)
            self.assertEqual(store.load()["ui_style"], "glassmorphism")
            self.assertEqual(store.load()["tps_match_mode"], "adaptive")
            self.assertFalse(store.load()["auto_paper_monitor_enabled"])
            saved = store.save({"capital": "250000", "risk_percent": "0.5", "daily_loss_percent": "2", "max_trades_per_day": "3", "theme": "light"})
            self.assertEqual(saved["max_trades_per_day"], 3)
            self.assertEqual(store.load()["theme"], "light")
            self.assertEqual(store.load()["capital"], 250000.0)

    def test_auto_paper_monitor_opt_in_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = store.load()
            settings["auto_paper_monitor_enabled"] = True
            self.assertTrue(store.save(settings)["auto_paper_monitor_enabled"])
            self.assertTrue(store.load()["auto_paper_monitor_enabled"])

    def test_trade_plan_minimum_score_is_persisted_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = store.load()
            settings["trade_plan_min_score"] = 80
            self.assertEqual(store.save(settings)["trade_plan_min_score"], 80)
            settings["trade_plan_min_score"] = 10
            self.assertEqual(store.save(settings)["trade_plan_min_score"], 10)
            settings["trade_plan_min_score"] = -1
            with self.assertRaisesRegex(ValueError, "between 0 and 100"):
                store.save(settings)

    def test_selected_tps_checklist_is_persisted_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = store.load()
            settings.update({
                "tps_enabled_conditions": ["Price vs VWAP", "EMA 5/20/50 alignment"],
                "tps_required_matches": 1, "tps_match_mode": "count",
            })
            saved = store.save(settings)
            self.assertEqual(saved["tps_required_matches"], 1)
            self.assertEqual(len(saved["tps_enabled_conditions"]), 2)
            settings = store.load(); settings["tps_match_mode"] = "adaptive"
            self.assertEqual(store.save(settings)["tps_match_mode"], "adaptive")
            settings = store.load()
            settings["tps_required_matches"] = 3
            with self.assertRaisesRegex(ValueError, "fit within"):
                store.save(settings)

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

    def test_new_visual_themes_are_valid_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            saved = store.save({"capital": 100000, "risk_percent": 1, "daily_loss_percent": 3, "max_trades_per_day": 5, "theme": "emerald"})
            self.assertEqual(saved["theme"], "emerald")

    def test_ui_design_style_is_persisted_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = store.load()
            settings["ui_style"] = "brutalism"
            self.assertEqual(store.save(settings)["ui_style"], "brutalism")
            settings["ui_style"] = "unknown"
            with self.assertRaisesRegex(ValueError, "UI design style"):
                store.save(settings)

    def test_execution_and_calendar_controls_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = store.load()
            settings.update({"economic_calendar_api_key": "client:key", "event_feed_fail_closed": True,
                             "paper_trade_cooldown_minutes": 30, "minimum_rr_ratio": 2,
                             "maximum_option_spread_percent": 5, "minimum_option_volume": 500,
                             "trailing_stop_trigger_r": 1.5, "trailing_stop_lock_r": .5,
                             "time_exit_minutes_before_close": 15})
            saved = store.save(settings)
            self.assertEqual(saved["paper_trade_cooldown_minutes"], 30)
            self.assertTrue(saved["event_feed_fail_closed"])
            self.assertEqual(saved["minimum_rr_ratio"], 2)
