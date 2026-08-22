"""Central, persistent overtrading protection for Release 1.3.

The guard only controls simulated paper captures. TPS has no broker-order
endpoint; the explicit real-money commitment is a behavioural safety prompt.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


SAFE_STATES = {"CALM / STABLE"}
EMOTIONAL_STATES = (
    "CALM / STABLE", "TIRED", "STRESSED", "ANGRY",
    "FOMO / URGE TO TRADE", "REVENGE / RECOVER LOSS",
)


class OvertradingGuard:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            root = Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or Path.home())
            path = root / "TPS AI Trading Assistant" / "recovery_guard.json"
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _save(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name("recovery_guard.pending.json")
        pending.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(pending, self.path)

    @staticmethod
    def _local_now(now=None) -> datetime:
        return (now or datetime.now()).replace(tzinfo=None)

    def save_check_in(self, emotional_state: str, paper_only_commitment: bool, note: str = "", now=None) -> dict:
        emotional_state = str(emotional_state).strip().upper()
        if emotional_state not in EMOTIONAL_STATES:
            raise ValueError("Choose a valid emotional state.")
        current = self._local_now(now)
        check_in = {
            "trade_date": current.date().isoformat(),
            "saved_at": current.isoformat(timespec="seconds"),
            "emotional_state": emotional_state,
            "paper_only_commitment": bool(paper_only_commitment),
            "note": str(note).strip()[:500],
        }
        value = self._load()
        history = [item for item in value.get("check_ins", []) if item.get("trade_date") != check_in["trade_date"]]
        value["check_ins"] = (history + [check_in])[-120:]
        self._save(value)
        return check_in

    def today_check_in(self, now=None) -> dict | None:
        trade_date = self._local_now(now).date().isoformat()
        return next((item for item in reversed(self._load().get("check_ins", [])) if item.get("trade_date") == trade_date), None)

    def assess(self, settings: dict, database, now=None) -> dict:
        current = self._local_now(now)
        trade_date = current.strftime("%d-%m-%Y")
        progress = database.paper_trade_progress(trade_date)
        if not isinstance(progress, dict):
            progress = {}
        all_progress = database.paper_trade_progress()
        if not isinstance(all_progress, dict):
            all_progress = {}
        target = int(settings.get("recovery_min_paper_sessions", 30))

        if settings.get("paper_validation_testing_mode", False):
            testing_limit = min(20, max(1, int(settings.get("paper_validation_daily_limit", 20))))
            count = int(progress.get("trades", 0) or 0)
            blockers = []
            if count >= testing_limit:
                blockers.append(f"Paper-validation daily limit reached ({count}/{testing_limit})")
            return {
                "allowed": not blockers,
                "blockers": blockers,
                "warnings": [
                    "Paper Validation Testing Mode is ON: behavioural recovery locks are temporarily suspended for simulated trades only",
                    "Target, stop-loss, time-exit, event, data-quality and open-position safety monitoring remain active",
                ],
                "check_in": self.today_check_in(current),
                "mode": "PAPER VALIDATION TESTING",
                "paper_trades_today": count,
                "daily_limit": testing_limit,
                "loss_streak": int((database.paper_loss_streak() or {}).get("count", 0) or 0),
                "locked_until": None,
                "paper_sessions": int(all_progress.get("days", 0) or 0),
                "paper_session_target": target,
            }
        if not settings.get("recovery_mode_enabled", True):
            return {"allowed": True, "blockers": [], "warnings": ["Recovery Mode is disabled"], "check_in": None}

        blockers, warnings = [], []
        check_in = self.today_check_in(current)
        if not check_in:
            blockers.append("Daily Recovery check-in is incomplete")
        else:
            state = str(check_in.get("emotional_state", "")).upper()
            if state not in SAFE_STATES:
                blockers.append(f"Emotional state is {state}; new paper captures are paused for today")
            if not check_in.get("paper_only_commitment"):
                blockers.append("Paper-only safety commitment is not confirmed")

        normal_limit = int(settings.get("max_trades_per_day", 5))
        recovery_limit = min(normal_limit, int(settings.get("recovery_daily_trade_limit", 1)))
        if progress.get("trades", 0) >= recovery_limit:
            blockers.append(f"Recovery daily paper-trade limit reached ({progress.get('trades', 0)}/{recovery_limit})")

        streak = database.paper_loss_streak()
        if not isinstance(streak, dict):
            streak = {"count": 0, "latest_closed_at": None}
        streak_count = int(streak.get("count", 0) or 0)
        streak_limit = int(settings.get("recovery_loss_streak_limit", 2))
        locked_until = None
        if streak_count >= streak_limit and streak.get("latest_closed_at"):
            last_closed = datetime.fromisoformat(streak["latest_closed_at"]).replace(tzinfo=None)
            locked_until = last_closed + timedelta(
                hours=int(settings.get("recovery_lock_hours", 48))
            )
            if current < locked_until:
                blockers.append(
                    f"Consecutive-loss lock active until {locked_until.strftime('%d-%m-%Y %H:%M')} "
                    f"({streak_count} losses)"
                )

        if all_progress.get("days", 0) < target:
            warnings.append(f"Paper validation: {all_progress.get('days', 0)}/{target} sessions; real-money eligibility remains withheld")
        return {
            "allowed": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "check_in": check_in,
            "paper_trades_today": progress.get("trades", 0),
            "daily_limit": recovery_limit,
            "loss_streak": streak_count,
            "locked_until": locked_until.isoformat(timespec="minutes") if locked_until else None,
            "paper_sessions": all_progress.get("days", 0),
            "paper_session_target": target,
            "mode": "RECOVERY PROTECTION",
        }
