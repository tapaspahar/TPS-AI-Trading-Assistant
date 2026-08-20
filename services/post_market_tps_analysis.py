"""Evidence-led, date-wise Roman Hindi post-market journal generator."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, time, timedelta

from core.database_manager import Database


def _details(row) -> dict:
    try:
        value = json.loads(row["details_json"] or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _candidate_evaluation(row, details: dict) -> tuple[dict, dict]:
    chart = ((details.get("attempt") or {}).get("chart") or {})
    strategy = chart.get("strategy") or {}
    candidate = str(row["candidate"] or strategy.get("candidate") or "").upper()
    evaluation = (strategy.get("side_evaluations") or {}).get(candidate) or strategy
    return strategy, evaluation


def _short_time(value: str | None) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M")
    except (TypeError, ValueError):
        return "time unavailable"


def _normalise_blocker(text: str) -> str:
    lowered = text.lower()
    if "fresh" in lowered or "trigger" in lowered or "pullback" in lowered:
        return "fresh entry trigger / pullback missing"
    if "fake" in lowered or "rejection" in lowered:
        return "fake-breakout ya rejection-wick risk"
    if "atr" in lowered or "extended" in lowered or "late" in lowered:
        return "ATR ke hisab se entry late/extended"
    if "support" in lowered or "resistance" in lowered or "room" in lowered:
        return "support/resistance ke bahut paas"
    if "rsi" in lowered or "chase" in lowered:
        return "RSI chase risk"
    if "volume" in lowered:
        return "directional volume confirmation missing"
    return text.strip()[:140] or "unspecified safety blocker"


def _missing_ranges(observed: set[datetime], day: datetime) -> tuple[int, list[str]]:
    start = day.replace(hour=9, minute=15, second=0, microsecond=0)
    expected = [start + timedelta(minutes=5 * index) for index in range(75)]
    missing = [point for point in expected if point not in observed]
    ranges: list[str] = []
    if missing:
        range_start = previous = missing[0]
        for point in missing[1:]:
            if point - previous != timedelta(minutes=5):
                ranges.append(f"{range_start:%H:%M}-{(previous + timedelta(minutes=5)):%H:%M}")
                range_start = point
            previous = point
        ranges.append(f"{range_start:%H:%M}-{(previous + timedelta(minutes=5)):%H:%M}")
    return len(expected), ranges


def build_post_market_analysis(database: Database, trade_date: str, now: datetime | None = None) -> dict:
    """Build one reproducible Roman Hindi note from persisted TPS evidence."""
    from core.market_session import parse_session_times
    _, session_open, session_close = parse_session_times()
    last_candle_start = (datetime.combine(datetime.today(), session_close) - timedelta(minutes=5)).time()
    day = datetime.strptime(trade_date, "%d-%m-%Y")
    generated = now or datetime.now()
    attempts = database.get_auto_trade_attempts(trade_date, limit=5000)
    trades = database.get_trades_for_date(trade_date)
    snapshots = database.get_market_snapshots(trade_date)

    evaluated = [row for row in attempts if row["outcome"] in ("STRATEGY REJECT", "SAFETY BLOCK", "CANDIDATE", "CAPTURED", "NO TRADE", "TRADE CAPTURED")]
    captured = [row for row in attempts if row["outcome"] in ("CAPTURED", "TRADE CAPTURED")]
    retry_rows = [row for row in attempts if row["outcome"] in ("DATA GAP", "RETRY PENDING", "SKIPPED")]
    candidate_counts = Counter(str(row["candidate"] or "MIXED") for row in evaluated)
    failed_conditions: Counter[str] = Counter()
    hard_blockers: Counter[str] = Counter()
    score_pass = checklist_pass = both_pass = 0
    best_attempts: list[dict] = []
    attempt_audit: list[dict] = []
    observed: set[datetime] = set()

    for row in attempts:
        try:
            candle = datetime.fromisoformat(str(row["candle_time"])).replace(tzinfo=None)
            if candle.date() == day.date() and session_open <= candle.time() <= last_candle_start:
                observed.add(candle.replace(second=0, microsecond=0))
        except (TypeError, ValueError):
            pass
        if row not in evaluated:
            attempt_audit.append(
                {
                    "sort": str(row["candle_time"] or row["checked_at"] or ""),
                    "text": (
                        f"- {_short_time(row['candle_time'] or row['checked_at'])} {row['candidate'] or '-'}: "
                        f"complete trade evaluation nahi hui; {row['outcome']}. Reason: {row['status_text']}"
                    ),
                }
            )
            continue
        details = _details(row)
        strategy, evaluation = _candidate_evaluation(row, details)
        selected = evaluation.get("selected_confirmations") or strategy.get("selected_confirmations") or []
        for condition in selected:
            if not condition.get("passed"):
                failed_conditions[str(condition.get("name") or "Unknown condition")] += 1
        blockers = evaluation.get("hard_blockers") or strategy.get("hard_blockers") or []
        # One evaluation can describe the same safety block in multiple
        # sentences. Count the affected candle once per normalized reason.
        for blocker in {_normalise_blocker(str(value)) for value in blockers}:
            hard_blockers[blocker] += 1
        score_ok = bool(evaluation.get("score_matched"))
        checklist_ok = bool(evaluation.get("checklist_matched"))
        score_pass += int(score_ok)
        checklist_pass += int(checklist_ok)
        both_pass += int(score_ok and checklist_ok)
        best_attempts.append(
            {
                "time": _short_time(row["candle_time"]),
                "candidate": str(row["candidate"] or "-").upper(),
                "score": int(row["score"] or 0),
                "passed": int(row["confirmations_passed"] or 0),
                "total": int(row["confirmations_total"] or 0),
                "blockers": [_normalise_blocker(str(value)) for value in blockers],
                "decision": str(row["decision"] or "NO TRADE"),
            }
        )
        passed_names = [str(value.get("name") or "condition") for value in selected if value.get("passed")]
        failed_names = [str(value.get("name") or "condition") for value in selected if not value.get("passed")]
        normalized_blockers = sorted({_normalise_blocker(str(value)) for value in blockers})
        if row["outcome"] in ("CAPTURED", "TRADE CAPTURED"):
            why = "trade liya kyunki " + (", ".join(passed_names) or "strategy aur safety gates pass hue")
        else:
            reasons = failed_names + normalized_blockers
            why = "trade nahi liya kyunki " + (", ".join(reasons) or str(row["status_text"] or "final plan gate pass nahi hua"))
        attempt_audit.append(
            {
                "sort": str(row["candle_time"] or row["checked_at"] or ""),
                "text": (
                    f"- {_short_time(row['candle_time'])} {row['candidate'] or '-'} | {row['outcome']} | "
                    f"score {int(row['score'] or 0)}/100 | confirmations "
                    f"{int(row['confirmations_passed'] or 0)}/{int(row['confirmations_total'] or 0)}: {why}."
                ),
            }
        )

    best_attempts.sort(key=lambda item: (item["score"], item["passed"]), reverse=True)
    expected_slots, missing_ranges = _missing_ranges(observed, day)
    coverage = round(len(observed) * 100 / expected_slots, 1) if expected_slots else 0.0
    retry_reasons = Counter()
    for row in retry_rows:
        text = f"{row['status_text']} {json.dumps(_details(row), ensure_ascii=False)}".lower()
        if "candle service is busy" in text:
            retry_reasons["Angel One candle service busy"] += 1
        elif "score" in text and "volume" in text:
            retry_reasons["trade-plan volume gate mismatch"] += 1
        elif "option" in text and ("timeout" in text or "timed out" in text):
            retry_reasons["Angel One option-chain timeout"] += 1
        else:
            retry_reasons["data/service retry"] += 1

    lines = [
        "POST MARKET ANALYSIS OF TPS",
        f"Trading date: {trade_date}",
        f"Report generate hua: {generated.strftime('%d-%m-%Y %H:%M:%S')}",
        "",
        "1. Aaj ka seedha result",
    ]
    if captured:
        lines.append(f"TPS ne {len(captured)} automatic paper trade capture kiye.")
        for row in sorted(captured, key=lambda value: str(value["candle_time"] or "")):
            lines.append(
                f"- {_short_time(row['candle_time'])}: {row['candidate'] or '-'} capture hua; "
                f"score {int(row['score'] or 0)}/100 aur confirmations "
                f"{int(row['confirmations_passed'] or 0)}/{int(row['confirmations_total'] or 0)} the."
            )
    else:
        lines.append("Aaj TPS se koi automatic paper trade capture nahi hua.")
    if trades:
        lines.append(f"Trade Journal me is date ke {len(trades)} trade record mile (manual aur automatic dono ho sakte hain).")

    lines.extend(
        [
            "",
            "2. Auto-check coverage",
            f"Total saved attempts: {len(attempts)}; complete evaluations: {len(evaluated)}; retry/skip: {len(retry_rows)}.",
            f"5-minute market slots me {len(observed)}/{expected_slots} coverage mili ({coverage:.1f}%).",
        ]
    )
    if missing_ranges:
        lines.append("Missing time ranges: " + ", ".join(missing_ranges) + ". In gaps me TPS decision ka proof available nahi hai.")
    if candidate_counts:
        lines.append("Candidate watch: " + ", ".join(f"{key} {value}" for key, value in candidate_counts.items()) + ".")
    else:
        lines.append("Candidate watch ka koi saved record available nahi hai.")

    lines.extend(["", "3. Trade kyon nahi hua / rejection ka main reason"])
    if evaluated:
        lines.append(
            f"Score threshold {score_pass} evaluations me pass hua; checklist {checklist_pass} me pass hui; "
            f"dono ek saath {both_pass} evaluations me pass hue. Final safety blockers ke baad {len(captured)} capture bache."
        )
    if failed_conditions:
        lines.append("Sabse zyada fail conditions: " + "; ".join(f"{name} ({count})" for name, count in failed_conditions.most_common(6)) + ".")
    if hard_blockers:
        lines.append("Final hard blockers: " + "; ".join(f"{name} ({count})" for name, count in hard_blockers.most_common(6)) + ".")
    if retry_reasons:
        lines.append("System/data retries: " + "; ".join(f"{name} ({count})" for name, count in retry_reasons.most_common()) + ".")
    if not evaluated:
        lines.append("Complete candle evaluation record nahi mila, isliye strategy performance ka conclusion nahi nikala ja sakta.")

    lines.extend(["", "4. Aaj ke best near-setups"])
    if best_attempts:
        for item in best_attempts[:5]:
            blocker_text = ", ".join(item["blockers"]) if item["blockers"] else "score/checklist ya plan gate"
            lines.append(
                f"- {item['time']} {item['candidate']}: score {item['score']}/100, "
                f"confirmations {item['passed']}/{item['total']}; capture nahi hua kyunki {blocker_text}."
            )
    else:
        lines.append("Near-setup compare karne ke liye evaluated candle data available nahi tha.")

    lines.extend(["", "5. Har saved trade attempt ka candle-wise record"])
    if attempt_audit:
        lines.extend(item["text"] for item in sorted(attempt_audit, key=lambda item: item["sort"]))
    else:
        lines.append("Is date par koi saved automatic trade attempt nahi mila.")

    lines.extend(
        [
            "",
            "6. TPS ka post-market conclusion",
            "Aaj 'trade nahi mila' ka matlab sirf market me opportunity nahi thi, aisa maanna sahi nahi hoga. "
            "TPS ke saved evidence me strategy rejection aur monitoring gaps dono ko alag dekhna zaroori hai.",
            "Agli review me best rejected candles ko actual chart ke saath compare karein. Safety rule ko sirf ek din ke result par loose na karein; pehle repeated evidence aur forward-test outcome dekhein.",
            "",
            "Note: Ye paper-trading audit hai, guaranteed prediction ya broker order nahi.",
        ]
    )

    metrics = {
        "source_attempt_count": len(attempts),
        "source_trade_count": len(trades),
        "source_snapshot_count": len(snapshots),
        "latest_checked_at": max((str(row["checked_at"]) for row in attempts), default=""),
        "evaluated": len(evaluated),
        "captured": len(captured),
        "retry_or_skipped": len(retry_rows),
        "expected_slots": expected_slots,
        "observed_slots": len(observed),
        "coverage_percent": coverage,
        "missing_ranges": missing_ranges,
        "candidate_counts": dict(candidate_counts),
        "score_pass": score_pass,
        "checklist_pass": checklist_pass,
        "score_and_checklist_pass": both_pass,
        "failed_conditions": dict(failed_conditions),
        "hard_blockers": dict(hard_blockers),
        "retry_reasons": dict(retry_reasons),
        "best_attempts": best_attempts[:10],
        "attempt_audit_count": len(attempt_audit),
    }
    return {
        "trade_date": trade_date,
        "generated_at": generated.isoformat(timespec="seconds"),
        "title": "Post Market Analysis of TPS",
        "summary_text": "\n".join(lines),
        "metrics": metrics,
    }


def generate_and_save_post_market_analysis(database: Database, trade_date: str, now: datetime | None = None) -> dict:
    analysis = build_post_market_analysis(database, trade_date, now=now)
    analysis["id"] = database.save_post_market_tps_analysis(analysis)
    return analysis


def _source_signature(database: Database, trade_date: str) -> tuple[int, int, int, str]:
    attempts = database.get_auto_trade_attempts(trade_date, limit=5000)
    trades = database.get_trades_for_date(trade_date)
    snapshots = database.get_market_snapshots(trade_date)
    latest = max((str(row["checked_at"]) for row in attempts), default="")
    return len(attempts), len(trades), len(snapshots), latest


def ensure_completed_post_market_reports(
    database: Database,
    now: datetime | None = None,
    limit: int = 60,
) -> list[str]:
    """Generate missing/stale reports after close and backfill past dates.

    The one-minute close buffer lets the configured final candle audit finish first.
    A later attempt/trade/snapshot changes the source signature, so the report
    is refreshed automatically on the next scheduler tick.
    """
    from core.market_session import parse_session_times
    _, _, session_close = parse_session_times()
    report_time = (datetime.combine(datetime.today(), session_close) + timedelta(minutes=1)).time()
    current = now or datetime.now()
    updated_dates: list[str] = []
    source_dates = database.get_post_market_source_dates()
    current_trade_date = current.strftime("%d-%m-%Y")
    if current.weekday() < 5 and current.time() >= report_time and current_trade_date not in source_dates:
        # If TPS stayed open but no attempt was made, that zero-activity fact is
        # itself important and must be recorded instead of silently vanishing.
        source_dates.insert(0, current_trade_date)
    for trade_date in source_dates[: max(1, int(limit))]:
        day = datetime.strptime(trade_date, "%d-%m-%Y").date()
        if day > current.date() or (day == current.date() and current.time() < report_time):
            continue
        signature = _source_signature(database, trade_date)
        if not any(signature[:3]) and trade_date != current_trade_date:
            continue
        existing = database.get_post_market_tps_analysis(trade_date)
        stale = existing is None
        if existing is not None:
            try:
                metrics = json.loads(existing["metrics_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                metrics = {}
            saved_signature = (
                int(metrics.get("source_attempt_count", -1)),
                int(metrics.get("source_trade_count", -1)),
                int(metrics.get("source_snapshot_count", -1)),
                str(metrics.get("latest_checked_at", "")),
            )
            stale = saved_signature != signature
        if stale:
            generate_and_save_post_market_analysis(database, trade_date, now=current)
            updated_dates.append(trade_date)
    return updated_dates
