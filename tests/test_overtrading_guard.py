import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core.overtrading_guard import OvertradingGuard


class FakeDatabase:
    def __init__(self, today=0, days=0, losses=0, latest_closed_at=None):
        self.today = today
        self.days = days
        self.losses = losses
        self.latest_closed_at = latest_closed_at

    def paper_trade_progress(self, trade_date=None):
        if trade_date:
            return {"trades": self.today, "days": 1 if self.today else 0}
        return {"trades": self.today, "days": self.days}

    def paper_loss_streak(self):
        return {"count": self.losses, "latest_closed_at": self.latest_closed_at}


class OvertradingGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.guard = OvertradingGuard(Path(self.temp.name) / "guard.json")
        self.now = datetime(2026, 8, 13, 10, 0)
        self.settings = {
            "recovery_mode_enabled": True,
            "max_trades_per_day": 5,
            "recovery_daily_trade_limit": 1,
            "recovery_loss_streak_limit": 2,
            "recovery_lock_hours": 48,
            "recovery_min_paper_sessions": 30,
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_check_in_blocks_capture(self):
        result = self.guard.assess(self.settings, FakeDatabase(), self.now)
        self.assertFalse(result["allowed"])
        self.assertTrue(any("check-in" in item for item in result["blockers"]))

    def test_calm_paper_only_check_in_allows_bounded_observation(self):
        self.guard.save_check_in("CALM / STABLE", True, now=self.now)
        result = self.guard.assess(self.settings, FakeDatabase(days=4), self.now)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["daily_limit"], 1)
        self.assertTrue(result["warnings"])

    def test_fomo_state_blocks_capture(self):
        self.guard.save_check_in("FOMO / URGE TO TRADE", True, now=self.now)
        result = self.guard.assess(self.settings, FakeDatabase(), self.now)
        self.assertFalse(result["allowed"])
        self.assertTrue(any("FOMO" in item for item in result["blockers"]))

    def test_daily_limit_and_consecutive_loss_lock_are_hard_blocks(self):
        self.guard.save_check_in("CALM / STABLE", True, now=self.now)
        last_loss = (self.now - timedelta(hours=2)).isoformat(timespec="seconds")
        result = self.guard.assess(
            self.settings,
            FakeDatabase(today=1, losses=2, latest_closed_at=last_loss),
            self.now,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("daily paper-trade limit" in item for item in result["blockers"]))
        self.assertTrue(any("Consecutive-loss lock" in item for item in result["blockers"]))

    def test_paper_validation_testing_mode_bypasses_recovery_but_stops_at_twenty(self):
        settings = {**self.settings, "paper_validation_testing_mode": True, "paper_validation_daily_limit": 20}
        allowed = self.guard.assess(settings, FakeDatabase(today=19, losses=5), self.now)
        self.assertTrue(allowed["allowed"])
        self.assertEqual(allowed["mode"], "PAPER VALIDATION TESTING")
        self.assertEqual(allowed["daily_limit"], 20)
        blocked = self.guard.assess(settings, FakeDatabase(today=20, losses=5), self.now)
        self.assertFalse(blocked["allowed"])
        self.assertTrue(any("20/20" in item for item in blocked["blockers"]))


if __name__ == "__main__":
    unittest.main()
