"""Shared evidence and attempt-outcome vocabulary for Release 1.4.1.

The trading engine must distinguish an observed false condition from evidence
that was never supplied.  Missing evidence is never silently converted to a
PASS or a strategy rejection.
"""
from __future__ import annotations

from enum import Enum


class EvidenceState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


ATTEMPT_OUTCOMES = (
    "DATA GAP",
    "SAFETY BLOCK",
    "STRATEGY REJECT",
    "CANDIDATE",
    "CAPTURED",
)


def evidence_state(value) -> EvidenceState:
    """Return a strict three-state interpretation without bool(None) loss."""
    if value is None or value == "":
        return EvidenceState.UNKNOWN
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"UNKNOWN", "UNAVAILABLE", "N/A", "NA", "NONE"}:
            return EvidenceState.UNKNOWN
        if normalized in {"TRUE", "YES", "Y", "1", "ACTIVE", "DETECTED"}:
            return EvidenceState.TRUE
        if normalized in {"FALSE", "NO", "N", "0", "CLEAR", "NOT DETECTED"}:
            return EvidenceState.FALSE
    return EvidenceState.TRUE if bool(value) else EvidenceState.FALSE


def unique_messages(values) -> list[str]:
    """Preserve order while preventing one fact being counted repeatedly."""
    seen = set()
    output = []
    for value in values or []:
        text = str(value).strip()
        key = " ".join(text.lower().split())
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def classify_attempt(*, captured=False, candidate=False, data_gaps=None, safety_blockers=None) -> str:
    """Apply one stable mutually-exclusive audit outcome."""
    if captured:
        return "CAPTURED"
    if safety_blockers:
        return "SAFETY BLOCK"
    if data_gaps:
        return "DATA GAP"
    if candidate:
        return "CANDIDATE"
    return "STRATEGY REJECT"
