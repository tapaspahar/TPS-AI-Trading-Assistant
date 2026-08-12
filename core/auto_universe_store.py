"""Short-lived local cache for automatically selected F&O research candidates."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class AutoUniverseStore:
    def __init__(self, path: str | Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant"
        self.path = Path(path) if path else base / "auto_fno_universe.json"

    def load(self, max_age_minutes: int | None = None) -> list[dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            refreshed = datetime.fromisoformat(str(payload.get("refreshed_at")))
            rows = payload.get("rows")
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return []
        if max_age_minutes is not None and datetime.now().astimezone() - _aware(refreshed) > timedelta(minutes=max_age_minutes):
            return []
        return [row for row in rows or [] if isinstance(row, dict) and row.get("underlying") and row.get("token")]

    def save(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"refreshed_at": datetime.now().astimezone().isoformat(timespec="seconds"), "rows": rows}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path)


def _aware(value: datetime) -> datetime:
    return value.astimezone() if value.tzinfo else value.astimezone()
