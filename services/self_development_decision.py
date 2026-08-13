"""Explainable post-market diagnostics for TPS development decisions.

This module never edits strategy rules or source code.  It turns persisted
post-market evidence into reviewable development suggestions so a single
market day cannot silently change production behaviour.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from core.database_manager import Database


def _json(value: str | None, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _historical_repeat_context(database: Database, metrics: dict, limit: int = 10) -> dict[str, int]:
    """Count how many recent reports contain today's important diagnostics."""
    current_keys = set(metrics.get("hard_blockers") or {}) | set(metrics.get("failed_conditions") or {})
    counts = Counter()
    for row in database.get_post_market_tps_analyses(limit=limit):
        old = _json(row["metrics_json"], {})
        present = set(old.get("hard_blockers") or {}) | set(old.get("failed_conditions") or {})
        for key in current_keys & present:
            counts[key] += 1
    return dict(counts)


def build_self_development_review(database: Database, trade_date: str, now: datetime | None = None) -> dict:
    """Create one evidence-led daily software rectification review."""
    source = database.get_post_market_tps_analysis(trade_date)
    if source is None:
        raise ValueError(f"Post-market analysis is not available for {trade_date}.")
    metrics = _json(source["metrics_json"], {})
    attempts = int(metrics.get("source_attempt_count") or 0)
    evaluated = int(metrics.get("evaluated") or 0)
    captured = int(metrics.get("captured") or 0)
    retry_count = int(metrics.get("retry_or_skipped") or 0)
    coverage = float(metrics.get("coverage_percent") or 0)
    snapshots = int(metrics.get("source_snapshot_count") or 0)
    both_pass = int(metrics.get("score_and_checklist_pass") or 0)
    failed = {str(k): int(v) for k, v in (metrics.get("failed_conditions") or {}).items()}
    blockers = {str(k): int(v) for k, v in (metrics.get("hard_blockers") or {}).items()}
    retry_reasons = {str(k): int(v) for k, v in (metrics.get("retry_reasons") or {}).items()}
    best = list(metrics.get("best_attempts") or [])
    repeats = _historical_repeat_context(database, metrics)
    trades = database.get_trades_for_date(trade_date)
    target_hits = sum(str(row["outcome"]).upper() == "TARGET HIT" for row in trades)
    stop_hits = sum("STOP" in str(row["outcome"]).upper() for row in trades)
    suggestions: list[dict] = []

    def add(key: str, priority: str, area: str, observation: str, evidence: str, suggestion: str, validation: str):
        suggestions.append({
            "key": key, "priority": priority, "area": area, "observation": observation,
            "evidence": evidence, "suggestion": suggestion, "validation": validation, "status": "OPEN",
        })

    if attempts == 0 or evaluated == 0:
        add(
            "evaluation_pipeline", "CRITICAL", "Auto-evaluation pipeline",
            "Complete candle evaluation evidence missing hai.",
            f"Saved attempts {attempts}; complete evaluations {evaluated}; coverage {coverage:.1f}%.",
            "Scheduler heartbeat, broker connection, completed-candle trigger aur exception audit ko ek health panel me jodein.",
            "Next 3 trading sessions me 09:15–15:30 expected slots aur saved evaluations reconcile karein.",
        )
    if coverage < 85:
        priority = "CRITICAL" if coverage < 50 else "HIGH"
        add(
            "coverage_gap", priority, "Monitoring coverage",
            "Trading-session coverage development decisions ke liye insufficient hai.",
            f"Expected 5-minute coverage ke mukable {coverage:.1f}%; missing ranges: {', '.join(metrics.get('missing_ranges') or []) or 'not itemized'}.",
            "Persistent scheduler heartbeat, missed-slot backfill aur data-gap reason codes add/strengthen karein.",
            "Kam se kam 3 consecutive sessions me 95%+ coverage prove hone par resolved mark karein.",
        )
    if retry_count:
        reason_text = "; ".join(f"{name} ({count})" for name, count in retry_reasons.items()) or "unspecified retries"
        add(
            "broker_reliability", "HIGH" if retry_count >= 5 else "MEDIUM", "Broker/data reliability",
            "Data/service retries ne decision opportunities ko skip ya delay kiya.",
            f"Retry/skip {retry_count}/{max(attempts, 1)}; {reason_text}.",
            "Single-flight request queue, bounded exponential retry, last-good-data age aur provider-specific rate telemetry implement/review karein.",
            "Replay test plus 3 live sessions me duplicate request, stale candle aur skipped slot count compare karein.",
        )
    if evaluated >= 10 and captured == 0:
        highest = max((int(item.get("score") or 0) for item in best), default=0)
        priority = "HIGH" if both_pass else "MEDIUM"
        add(
            "zero_capture_calibration", priority, "Signal calibration",
            "Market scan hua, lekin ek bhi automatic paper trade capture nahi hua.",
            f"Evaluations {evaluated}; score+checklist pass {both_pass}; best score {highest}/100; capture 0.",
            "Best rejected candles ka counterfactual replay banayein: existing rule aur proposed change ko same candles par side-by-side compare karein. Rule ko direct loose na karein.",
            "Minimum 30 forward samples aur target-vs-stop outcome ke bina production threshold change approve na karein.",
        )
    late_count = sum(count for name, count in blockers.items() if any(word in name.lower() for word in ("late", "extended", "fresh", "pullback")))
    if late_count:
        repeat_days = max((repeats.get(name, 0) for name in blockers if any(word in name.lower() for word in ("late", "extended", "fresh", "pullback"))), default=1)
        add(
            "entry_timing", "HIGH" if repeat_days >= 3 else "MEDIUM", "Entry timing",
            "Setup identify hone aur entry eligibility ke beech delay/fresh-trigger mismatch dikh raha hai.",
            f"Aaj {late_count} affected evaluations; recent history me up to {repeat_days}/10 report days par same family mili.",
            "Signal-discovery time, first-valid-trigger time aur final-capture time alag fields me log karke early-watch notification study karein.",
            "Replay me look-ahead ke bina first valid candle compare karein; false entries badhe bina timing improve honi chahiye.",
        )
    volume_count = sum(count for name, count in {**failed, **blockers}.items() if "volume" in name.lower())
    if volume_count and evaluated:
        add(
            "volume_evidence", "MEDIUM", "Directional-volume evidence",
            "Volume evidence frequently decision ko reject kar raha hai.",
            f"Volume-related failures/blockers {volume_count}; complete evaluations {evaluated}.",
            "Missing provider volume, low-VIX regime aur genuinely weak participation ko separate reason codes/benchmarks se classify karein.",
            "Raw volume availability validate karke regime-wise walk-forward comparison karein; missing data ko PASS kabhi na banayein.",
        )
    level_count = sum(count for name, count in {**failed, **blockers}.items() if "support" in name.lower() or "resistance" in name.lower())
    if level_count:
        add(
            "level_context", "MEDIUM", "Support/resistance context",
            "Chart/OI level safety repeatedly setup ko block kar rahi hai.",
            f"Level-related failures {level_count}; snapshots {snapshots}.",
            "Chart zone aur OI wall ko separately persist karke agreement, distance-in-ATR aur stale-level age report karein.",
            "Historical replay me breakout/retest outcome compare karein; near-level safety ko single-day result par remove na karein.",
        )
    if captured > 5:
        add(
            "overtrading_guard", "HIGH", "Risk and overtrading",
            "Daily paper captures unusually high hain.",
            f"Captured paper trades {captured}; journal rows {len(trades)}.",
            "Same-direction duplicate, cooldown aur daily trade-cap enforcement audit karein.",
            "Every capture ko unique completed candle/contract se reconcile karke risk cap verify karein.",
        )
    if stop_hits > target_hits and stop_hits:
        add(
            "outcome_quality", "HIGH", "Entry/exit outcome quality",
            "Recorded stop outcomes target outcomes se zyada hain.",
            f"Target hits {target_hits}; stop outcomes {stop_hits}; recorded trades {len(trades)}.",
            "Entry lateness, premium spread, initial ATR stop aur MFE/MAE fields ko post-mortem dataset me compare karein.",
            "At least 30 decisive paper outcomes par rule-version report se improvement prove karein.",
        )
    validation = database.get_validation_report()
    if int(validation.get("samples") or 0) < 30:
        add(
            "sample_size", "INFO", "Validation confidence",
            "Live outcome sample structural rule change justify karne ke liye chhota hai.",
            f"Fully confirmed closed samples {validation.get('samples', 0)}/30; measured accuracy {validation.get('accuracy', 0):.1f}%.",
            "Current version tag ke saath fixed-risk paper validation continue karein.",
            "30+ fully confirmed closed samples aur at least 20 decisive target/stop outcomes ke baad review karein.",
        )
    if not suggestions:
        add(
            "healthy_monitor", "INFO", "System health",
            "Aaj ke persisted evidence me immediate software defect signal nahi mila.",
            f"Coverage {coverage:.1f}%; evaluations {evaluated}; retries {retry_count}; captures {captured}.",
            "Current rules ko unchanged rakhkar monitoring aur forward validation continue karein.",
            "Repeated evidence aane par hi development proposal open karein.",
        )

    penalties = 0
    penalties += min(40, round(max(0.0, 90.0 - coverage) * 0.7))
    penalties += min(20, retry_count * 3)
    penalties += 20 if evaluated == 0 else 0
    penalties += 10 if attempts >= 10 and captured == 0 and both_pass > 0 else 0
    penalties += min(10, stop_hits * 3) if stop_hits > target_hits else 0
    health = max(0, min(100, 100 - penalties))
    verdict = "NEEDS ATTENTION" if health < 50 else "REVIEW REQUIRED" if health < 75 else "STABLE / MONITOR"
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
    suggestions.sort(key=lambda item: (priority_order[item["priority"]], item["area"]))
    generated = now or datetime.now().astimezone()
    lines = [
        "AI SELF-DEVELOPMENT DECISION CENTER",
        f"Trading date: {trade_date} | System health: {health}/100 | Verdict: {verdict}",
        "",
        "Ye explainable AI review saved TPS evidence se development suggestions banata hai. Ye code ya trading rules khud change nahi karta.",
        f"Evidence: attempts {attempts}, evaluations {evaluated}, coverage {coverage:.1f}%, retries {retry_count}, captures {captured}, journal trades {len(trades)}.",
        "",
        "Suggested rectifications:",
    ]
    for index, item in enumerate(suggestions, 1):
        lines.extend([
            f"{index}. [{item['priority']}] {item['area']}",
            f"Observation: {item['observation']}",
            f"Evidence: {item['evidence']}",
            f"Development suggestion: {item['suggestion']}",
            f"Approval test: {item['validation']}",
            "",
        ])
    lines.append("Safety: Pehle replay/backtest, phir fixed-risk paper forward test, aur uske baad human approval. Automatic source-code modification disabled hai.")
    return {
        "trade_date": trade_date,
        "generated_at": generated.isoformat(timespec="seconds"),
        "source_generated_at": str(source["generated_at"]),
        "health_score": health,
        "verdict": verdict,
        "summary_text": "\n".join(lines),
        "suggestions": suggestions,
    }


def generate_and_save_self_development_review(
    database: Database, trade_date: str, now: datetime | None = None
) -> dict:
    review = build_self_development_review(database, trade_date, now=now)
    review["id"] = database.save_self_development_review(review)
    return review


def ensure_completed_self_development_reviews(database: Database, limit: int = 60) -> list[str]:
    """Backfill or refresh reviews whenever their post-market source changes."""
    updated = []
    for source in database.get_post_market_tps_analyses(limit=limit):
        existing = database.get_self_development_review(str(source["trade_date"]))
        if existing is None or str(existing["source_generated_at"]) != str(source["generated_at"]):
            generate_and_save_self_development_review(database, str(source["trade_date"]))
            updated.append(str(source["trade_date"]))
    return updated

