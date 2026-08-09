import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.market_session import IST
from services.economic_calendar_service import EconomicCalendarService


class EconomicCalendarServiceTests(unittest.TestCase):
    def test_cached_high_impact_event_blocks_inside_window(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "events.json"
            cache.write_text(json.dumps({
                "fetched_at": now.isoformat(),
                "events": [{"name": "RBI Interest Rate Decision", "country": "India", "time": now.isoformat(), "importance": 3}],
            }), encoding="utf-8")
            result = EconomicCalendarService("", cache).assess(now, 30)
            self.assertTrue(result["blocked"])
            self.assertEqual(result["status"], "HIGH-IMPACT EVENT WINDOW")

    def test_missing_key_never_invents_events(self):
        with tempfile.TemporaryDirectory() as directory:
            result = EconomicCalendarService("", Path(directory) / "missing.json").fetch()
            self.assertFalse(result["available"])
            self.assertEqual(result["events"], [])

