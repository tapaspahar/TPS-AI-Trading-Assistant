"""Best-effort broker reliability telemetry; never interrupts market analysis."""
from __future__ import annotations

from datetime import datetime
import os
from time import monotonic

from core.database_manager import Database


def start_request() -> tuple[float, str]:
    return monotonic(), datetime.now().astimezone().isoformat(timespec="milliseconds")


def record_request(provider: str, operation: str, started: tuple[float, str], *,
                   outcome: str, attempt_count: int = 1, cache_hit: bool = False,
                   data_timestamp=None, error_code=None, details: dict | None = None):
    # Pytest exposes this marker while a test is running. Test doubles and
    # mocks must never contaminate the operator's production reliability DB.
    if os.environ.get("PYTEST_CURRENT_TEST") or "mock" in str(provider).lower():
        return
    completed = datetime.now().astimezone()
    age = None
    if data_timestamp:
        try:
            age = max(0, int((completed.replace(tzinfo=None) -
                              datetime.fromisoformat(str(data_timestamp)).replace(tzinfo=None)).total_seconds()))
        except (TypeError, ValueError):
            pass
    event = {
        "provider": provider, "operation": operation, "started_at": started[1],
        "completed_at": completed.isoformat(timespec="milliseconds"),
        "duration_ms": round((monotonic() - started[0]) * 1000), "outcome": outcome,
        "attempt_count": attempt_count, "cache_hit": cache_hit,
        "data_timestamp": data_timestamp, "data_age_seconds": age,
        "error_code": error_code, "details": details or {},
    }
    database = None
    try:
        database = Database()
        database.save_broker_telemetry(event)
    except Exception:
        return
    finally:
        if database is not None:
            database.close()
