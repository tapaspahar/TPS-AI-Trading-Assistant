"""Strict, rate-aware forward paper trading. It never calls an order endpoint."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from core.overtrading_guard import OvertradingGuard
from engine.decision_engine import ChartSnapshot, DecisionEngine
from engine.live_setup_capture import build_live_capture
from engine.market_environment import analyze_market_environment
from engine.execution_safety import assess_execution_safety
from engine.expiry_strategy_engine import analyze_expiry_strategy
from engine.option_chain_engine import analyze_option_chain
from engine.trade_plan_engine import create_review_plan
from engine.tps_entry_confirmation import evaluate_tps_entry_v2
from engine.regular_scalp_validation import evaluate_regular_scalp_validation
from engine.evidence_model import classify_attempt, unique_messages
from engine.trade_outcome_memory import build_trade_fingerprint
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot
from services.economic_calendar_service import EconomicCalendarService
from services.provider_telemetry import record_request, start_request
from services.market_data_hub import MarketDataHub


def exploratory_paper_eligibility(strategy: dict, settings: dict) -> dict:
    """Allow a near-valid setup only for explicitly enabled PAPER validation.

    Direction, volume, data completeness and every hard blocker remain strict;
    only the configured checklist/score finish line may be relaxed.
    """
    candidate = str(strategy.get("candidate") or "").upper()
    side = (strategy.get("side_evaluations") or {}).get(candidate) or {}
    required = int(side.get("required", strategy.get("required", 0)) or 0)
    passed = int(side.get("passed", strategy.get("passed", 0)) or 0)
    score = int(side.get("score", strategy.get("score", 0)) or 0)
    allowance = max(0, min(2, int(settings.get("paper_validation_soft_miss_allowance", 2))))
    configured_score = int(strategy.get("minimum_score", settings.get("trade_plan_min_score", 95)) or 95)
    score_floor = max(60, configured_score - 25)
    misses = max(0, required - passed)
    confirmations = side.get("selected_confirmations") or strategy.get("selected_confirmations") or []
    volume_pass = any(
        item.get("name") == "Directional volume" and item.get("applicable", True) and item.get("passed")
        for item in confirmations
    )
    directional = bool((side.get("directional_consensus") or {}).get("passed"))
    hard_blockers = unique_messages(side.get("hard_blockers") or strategy.get("hard_blockers"))
    risk_blockers = unique_messages(side.get("risk_blockers") if "risk_blockers" in side else hard_blockers)
    data_gaps = unique_messages(side.get("data_gaps") or strategy.get("data_gaps"))
    standard_allowed = bool(
        settings.get("paper_validation_testing_mode") and candidate in {"CE", "PE"}
        and not strategy.get("trade_ready") and required > 0 and misses <= allowance
        and score >= score_floor and directional and volume_pass
        and not hard_blockers and not data_gaps
    )
    impulse_reversal = bool((side.get("impulse_reversal_validation") or {}).get("passed"))
    reversal_allowed = bool(
        settings.get("paper_validation_testing_mode") and candidate in {"CE", "PE"}
        and impulse_reversal and volume_pass and not risk_blockers and not data_gaps
    )
    allowed = standard_allowed or reversal_allowed
    return {
        "allowed": allowed, "candidate": candidate, "soft_misses": misses,
        "allowance": allowance, "score": score, "score_floor": score_floor,
        "directional_consensus": directional, "volume_confirmed": volume_pass,
        "hard_blockers": risk_blockers if reversal_allowed else hard_blockers, "data_gaps": data_gaps,
        "validation_track": "IMPULSE REVERSAL PAPER" if reversal_allowed else "EXPLORATORY PAPER",
        "impulse_reversal": impulse_reversal,
    }


def _attempt(status, checked_at, *, capture=None, chart=None, candidate=None, future=None, blockers=None, chain=None, timing=None,
             outcome=None, data_gaps=None, safety_blockers=None, warnings=None):
    """Return a transparent audit record for every automatic decision."""
    return {
        "status": status,
        "attempt": {
            "checked_at": checked_at.isoformat(timespec="seconds"),
            "candle_time": (capture or {}).get("candle_time"),
            "future_symbol": (future or {}).get("symbol"),
            "candidate": candidate,
            "capture": capture or {},
            "chart": chart or {},
            "chain": chain or {},
            "timing": timing or {},
            "blockers": unique_messages(blockers),
            "data_gaps": unique_messages(data_gaps),
            "safety_blockers": unique_messages(safety_blockers),
            "warnings": unique_messages(warnings),
            "primary_blocker": (unique_messages(safety_blockers) + unique_messages(data_gaps) + unique_messages(blockers) or [None])[0],
            "secondary_warnings": unique_messages(
                (unique_messages(safety_blockers) + unique_messages(data_gaps) + unique_messages(blockers))[1:] + unique_messages(warnings)
            ),
        },
        "attempt_outcome": outcome,
    }


def _record(database, symbol, result):
    result.setdefault("attempt", {})["symbol"] = str(symbol).upper()
    database.save_auto_trade_attempt(symbol, result)
    return result


def _completed_candles(candles, checked_at):
    """Exclude the currently forming 5-minute candle when the feed includes it."""
    if not candles:
        return candles
    bucket = checked_at.replace(minute=(checked_at.minute // 5) * 5, second=0, microsecond=0)
    try:
        latest_start = datetime.fromisoformat(str(candles[-1]["time"])).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        return candles
    return candles[:-1] if latest_start >= bucket.replace(tzinfo=None) else candles


def _completed_candle_age_seconds(candle_time, checked_at, interval_seconds=300):
    """Age since candle close; broker timestamps identify candle start."""
    opened_at = datetime.fromisoformat(str(candle_time)).replace(tzinfo=None)
    closed_at_seconds = opened_at.timestamp() + max(0, int(interval_seconds))
    return max(0, int(checked_at.replace(tzinfo=None).timestamp() - closed_at_seconds))


def signal_timing_stage(strategy: dict, settings: dict) -> str:
    """Classify timing without converting an early watch into an entry signal."""
    if strategy.get("trade_ready"):
        return "FIRST VALID"
    candidate = strategy.get("candidate")
    side = (strategy.get("side_evaluations") or {}).get(candidate) or {}
    required = int(strategy.get("required", settings.get("tps_required_matches", 5)) or 5)
    minimum_score = int(strategy.get("minimum_score", settings.get("trade_plan_min_score", 95)) or 95)
    passed = int(side.get("passed", strategy.get("passed", 0)) or 0)
    score = int(side.get("score", strategy.get("score", 0)) or 0)
    if candidate in {"CE", "PE"} and passed >= max(1, required - 1) and score >= max(0, minimum_score - 15):
        return "EARLY WATCH"
    return "NONE"


def _fallback_timing(stage: str, checked_at: datetime, candle_time: str | None) -> dict:
    timestamp = checked_at.isoformat(timespec="seconds")
    return {
        "stage": stage,
        "signal_discovery_at": timestamp if stage != "NONE" else None,
        "discovery_candle_time": candle_time if stage != "NONE" else None,
        "first_valid_trigger_at": timestamp if stage == "FIRST VALID" else None,
        "final_capture_at": None,
        "delay_seconds": 0 if stage == "FIRST VALID" else None,
        "no_look_ahead": True,
    }


def run_auto_paper_cycle(client, symbol: str, settings: dict, *, requested_lots: int = 1) -> dict:
    """Evaluate both sides and capture only after checklist, score and risk pass."""
    symbol = str(symbol).upper()
    database = Database()
    try:
        checked_at = datetime.now()
        today = checked_at.strftime("%d-%m-%Y")
        progress = database.paper_trade_progress(today)
        service = OptionContractService()
        future = service.get_front_month_future(symbol)
        provider = getattr(client, "provider_name", "Broker")
        request_started = start_request()
        try:
            candles = MarketDataHub.candles(client, future["exchange"], future["token"], "FIVE_MINUTE", 5)
        except Exception as error:
            record_request(provider, "auto-paper-candles", request_started, outcome="FAILURE",
                           error_code=type(error).__name__, details={"message": str(error)})
            raise
        record_request(provider, "auto-paper-candles", request_started, outcome="SUCCESS",
                       data_timestamp=candles[-1].get("time") if candles else None,
                       details={"rows": len(candles), "symbol": symbol})
        candles = _completed_candles(candles, checked_at)
        if len(candles) < 51:
            raise ValueError("At least 51 completed 5-minute candles are required for the automatic TPS v2 check.")
        capture = build_live_capture(symbol, "5m", candles, f"{provider} current-month future {future['symbol']}")
        capture["candle_time"] = candles[-1].get("time")
        capture["provider"] = provider
        try:
            capture["provider_data_age_seconds"] = _completed_candle_age_seconds(
                capture["candle_time"], checked_at,
            )
        except (TypeError, ValueError):
            capture["provider_data_age_seconds"] = None
        maximum_age = max(60, int(settings.get("market_data_max_age_seconds", 420) or 420))
        if capture["provider_data_age_seconds"] is None:
            reason = "Completed-candle timestamp is unavailable; provider success cannot be treated as fresh market data"
            result = _attempt(
                f"No paper trade: {reason}.", checked_at, capture=capture, candidate=None, future=future,
                outcome="DATA GAP", data_gaps=[reason],
            )
            return _record(database, symbol, result)
        if int(capture["provider_data_age_seconds"]) > maximum_age:
            reason = (
                f"Completed market candle is stale ({capture['provider_data_age_seconds']}s old; "
                f"maximum {maximum_age}s)"
            )
            result = _attempt(
                f"No paper trade: {reason}.", checked_at, capture=capture, candidate=None, future=future,
                outcome="DATA GAP", data_gaps=[reason],
                warnings=["Transport request succeeded, but the returned market evidence was not fresh"],
            )
            return _record(database, symbol, result)
        snapshot = ChartSnapshot(
            price=float(capture["close"]), ema_5=float(capture["ema_5"]), ema_20=float(capture["ema_20"]), ema_50=float(capture["ema_50"]),
            vwap=float(capture["vwap"]) if capture["vwap"] else None, supertrend=float(capture["supertrend"]),
            volume=float(capture["volume"]) if capture["volume"] else None, volume_ema=float(capture["volume_ema"]) if capture["volume_ema"] else None,
            rsi_14=float(capture["rsi_14"]) if capture["rsi_14"] else None, atr_14=float(capture["atr_14"]) if capture["atr_14"] else None,
            volume_ratio=float(capture["volume_ratio"]) if capture["volume_ratio"] else None, candle_direction=capture.get("candle_direction"),
            fake_breakout_risk=bool(capture.get("fake_breakout_risk")) if capture.get("fake_breakout_risk") is not None else False,
        )
        legacy_candidate = "CE" if snapshot.price > snapshot.supertrend else "PE"
        legacy_chart = DecisionEngine().evaluate(snapshot, legacy_candidate, "Calm")
        spot_config = UNDERLYING_QUOTES[symbol]
        spot = float(MarketDataHub.quote(client, spot_config["exchange"], spot_config["token"]).get("ltp", 0) or 0)
        if spot <= 0:
            reason = "Usable underlying spot quote is unavailable"
            result = _attempt(
                f"No paper trade: {reason.lower()}.", checked_at, capture=capture, chart=legacy_chart,
                candidate=None, future=future, outcome="DATA GAP", data_gaps=[reason],
            )
            return _record(database, symbol, result)
        contracts = contracts_near_spot(service.get_contracts(symbol), spot, wings=5)
        expiry = min(contract["expiry"] for contract in contracts)
        contracts = [contract for contract in contracts if contract["expiry"] == expiry]
        chain = analyze_option_chain(contracts, MarketDataHub.option_chain(client, contracts[0]["exchange"], [contract["token"] for contract in contracts]))
        try:
            vix_config = service.get_india_vix_instrument()
            india_vix = float(MarketDataHub.quote(client, vix_config["exchange"], vix_config["token"]).get("ltp", 0) or 0)
        except (RuntimeError, ValueError, TypeError, KeyError):
            india_vix = None
        event_risk = EconomicCalendarService(settings.get("economic_calendar_api_key", "")).assess(
            checked_at, settings.get("event_no_trade_minutes", 30)
        ) if settings.get("economic_calendar_enabled", True) else {
            "available": False, "blocked": False, "status": "DISABLED", "nearby_events": [],
            "risk_multiplier": 1.0, "confidence_penalty": 0,
        }
        expiry_date = expiry if hasattr(expiry, "year") else datetime.fromisoformat(str(expiry)).date()
        expiry_day = expiry_date == checked_at.date()
        environment = analyze_market_environment(candles, capture, spot, india_vix, checked_at, event_risk)
        environment["expiry_day"] = expiry_day
        environment["strategy_preference"] = (
            "HEDGE WATCH - ATM straddle/strangle research" if expiry_day and (
                environment["regime"] == "HIGH VOLATILITY" or event_risk.get("blocked")
            ) else "DIRECTIONAL CE/PE"
        )
        expiry_strategy = analyze_expiry_strategy(spot, chain, environment, (expiry_date - checked_at.date()).days)
        environment["expiry_strategy"] = expiry_strategy
        testing_mode = bool(settings.get("paper_validation_testing_mode", False))
        # Options Workspace validation is deliberately capped at ten samples
        # per day even if an older settings file contains the legacy value 20.
        testing_limit = min(10, max(1, int(settings.get("paper_validation_daily_limit", 10))))
        environment["adaptive_max_trades"] = testing_limit if testing_mode else min(
            int(settings.get("max_trades_per_day", 5)),
            1 if environment["vix_zone"] == "EXTREME RISK" else 2 if environment["regime"] == "LOW VOLATILITY" else int(settings.get("max_trades_per_day", 5)),
        )
        strategy = evaluate_tps_entry_v2(candles, capture, chain, settings, environment)
        exploratory = exploratory_paper_eligibility(strategy, settings)
        candidate = strategy["candidate"]
        selected_confirmations = strategy.get("selected_confirmations") or strategy.get("confirmations") or []
        side_evaluations = strategy.get("side_evaluations") or {}
        chart = {
            "symbol": symbol, "score": strategy["score"], "direction": strategy["direction"],
            "decision": strategy["decision"], "trade_ready": strategy["trade_ready"],
            "volume_confirmed": any(item["name"] == "Directional volume" and item["passed"] for item in selected_confirmations),
            "reasons": [f"{item['name']}: {item['detail']}" for item in selected_confirmations if item["passed"]],
            "warnings": strategy["blockers"] + [f"{item['name']}: {item['detail']}" for item in selected_confirmations if not item["passed"]],
            "strategy": strategy, "legacy_score": legacy_chart["score"],
            "ce_score": (side_evaluations.get("CE") or {}).get("score"),
            "pe_score": (side_evaluations.get("PE") or {}).get("score"),
            "market_environment": environment,
            "event_risk": event_risk,
            "provider": provider,
            "final_confidence": max(0, round(strategy["score"] * float(environment.get("risk_multiplier", 1)))),
        }
        chart["data_gaps"] = unique_messages(strategy.get("data_gaps"))
        # Keep the tri-state evidence map at the chart boundary as well as in
        # the nested strategy payload. Persistence/reporting consumers use
        # this stable boundary and must not silently lose UNKNOWN evidence.
        chart["evidence_states"] = dict(strategy.get("evidence_states") or {})
        chart["primary_blocker"] = strategy.get("primary_blocker")
        chart["secondary_warnings"] = unique_messages(strategy.get("secondary_warnings"))
        # This is deliberately an audit-only companion to strict TPS.  A READY
        # scalp verdict cannot enter the capture path below unless the normal
        # TPS strategy itself is also trade-ready.
        chart["regular_scalp_validation"] = evaluate_regular_scalp_validation(
            strategy, environment, capture, chain, settings,
        )
        timing_stage = signal_timing_stage(strategy, settings)
        timing = database.signal_timing_context(
            symbol, candidate or "-", checked_at.isoformat(timespec="seconds"), capture.get("candle_time"), timing_stage,
        )
        if not isinstance(timing, dict):
            timing = _fallback_timing(timing_stage, checked_at, capture.get("candle_time"))
        chart["signal_timing"] = timing
        daily_limit = float(settings.get("capital", 100000)) * float(settings.get("daily_loss_percent", 3)) / 100
        progress["daily_remaining"] = (
            float("inf") if testing_mode
            else max(0, daily_limit - max(0, -float(progress.get("realized_pnl", 0))))
        )
        operational_blockers = []
        recovery = OvertradingGuard().assess(settings, database, checked_at)
        if settings.get("news_risk_pause"): operational_blockers.append("Emergency News Risk Pause is ON")
        if event_risk.get("blocked") and not settings.get("event_risk_override"): operational_blockers.append("High-impact economic event no-trade window is active")
        if not event_risk.get("available") and settings.get("event_feed_fail_closed"): operational_blockers.append("Economic-calendar feed unavailable (fail-closed)")
        max_open = min(10, max(1, int(settings.get("paper_validation_max_open_trades", 10)))) if testing_mode else 1
        if int(progress["open_trades"]) >= max_open:
            operational_blockers.append(f"Concurrent open paper-trade limit reached ({progress['open_trades']}/{max_open})")
        adaptive_limit = environment["adaptive_max_trades"]
        if progress["trades"] >= adaptive_limit: operational_blockers.append(f"Adaptive daily paper-trade limit reached ({progress['trades']}/{adaptive_limit})")
        if progress["daily_remaining"] <= 0: operational_blockers.append("Daily loss limit exhausted")
        operational_blockers.extend(recovery.get("blockers") or [])
        chart["recovery_guard"] = recovery
        if operational_blockers:
            chart["warnings"].extend(operational_blockers)
            result = _attempt(
                "No new paper trade: TPS v2 candle evaluation completed but an operational safety limit blocked capture.",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=chart["warnings"], chain=chain, timing=timing,
                outcome="SAFETY BLOCK", safety_blockers=operational_blockers,
                data_gaps=strategy.get("data_gaps"), warnings=strategy.get("quality_warnings"),
            )
            return _record(database, symbol, result)
        if not strategy["trade_ready"] and not exploratory["allowed"]:
            data_gaps = unique_messages(strategy.get("data_gaps"))
            result = _attempt(
                f"No paper trade: {candidate} checklist {strategy['passed']}/{strategy.get('total', 7)} "
                f"(required {strategy.get('required', settings.get('tps_required_matches', 5))}) and score {strategy['score']}/100 "
                f"(required {strategy.get('minimum_score', settings.get('trade_plan_min_score', 95))}).",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=strategy.get("hard_blockers"), chain=chain, timing=timing,
                outcome=classify_attempt(
                    # EARLY WATCH and a named CE/PE side are observations, not
                    # qualified candidates.  A candidate must have passed the
                    # complete strategy gate; this branch is therefore a
                    # strategy rejection unless evidence is missing.
                    candidate=bool(strategy.get("trade_ready")),
                    data_gaps=data_gaps,
                ),
                data_gaps=data_gaps, warnings=strategy.get("quality_warnings"),
            )
            return _record(database, symbol, result)
        if exploratory["allowed"]:
            chart["exploratory_validation"] = exploratory
            chart["decision"] = (
                f"{exploratory['validation_track']} {candidate} — strong completed-candle reversal captured for validation"
                if exploratory.get("impulse_reversal") else
                f"EXPLORATORY PAPER {candidate} — {exploratory['soft_misses']} soft checklist miss(es)"
            )
            chart["trade_ready"] = False
            chart["warnings"].append(
                f"PAPER exploratory capture: {exploratory['soft_misses']}/{exploratory['allowance']} soft misses; "
                f"score {exploratory['score']}/{exploratory['score_floor']} exploratory floor"
            )
        plan_chart = dict(chart)
        if exploratory["allowed"]:
            plan_chart["direction"] = "BULLISH" if candidate == "CE" else "BEARISH"
            plan_chart["score"] = exploratory["score"]
            plan_chart["volume_confirmed"] = True
        plan_minimum_score = (
            0 if exploratory.get("impulse_reversal") else exploratory["score_floor"]
        ) if exploratory["allowed"] else int(settings.get("trade_plan_min_score", 95))
        plan = create_review_plan(
            symbol, spot, contracts, chain["quote_rows"], plan_chart, chain, settings,
            requested_lots=max(1, min(100, int(requested_lots))),
            minimum_score=plan_minimum_score,
        )
        plan["confidence"] = chart["final_confidence"]
        if exploratory.get("impulse_reversal") and plan.get("reasons"):
            plan["reasons"][0] = (
                f"Paper-only impulse reversal validation: {candidate}, completed candle volume/body/VWAP/SuperTrend aligned; "
                f"normal checklist score {strategy['score']}/100 remains visible"
            )
        plan["event_context"] = event_risk
        plan["rule_version"] = "TPS Entry Confirmation System v3 - independent CE/PE + selected checklist"
        plan["decision_audit"] = {
            "ce": side_evaluations.get("CE"), "pe": side_evaluations.get("PE"),
            "enabled_conditions": strategy.get("enabled_conditions"),
            "required_matches": strategy.get("required"), "required_score": strategy.get("minimum_score"),
            "hard_blockers": strategy.get("hard_blockers", []),
            "event_context": event_risk, "market_environment": environment,
            "validation_track": exploratory.get("validation_track") if exploratory["allowed"] else "STRICT PAPER",
            "exploratory_validation": exploratory if exploratory["allowed"] else None,
        }
        plan["strategy"] = {
            "candidate": candidate, "direction": strategy.get("direction"),
            "score": strategy.get("score"), "selected_confirmations": selected_confirmations,
        }
        plan["market_environment"] = environment
        selected_quote = next((row for row in chain["quote_rows"] if str(row.get("token")) == str(plan["contract"]["token"])), {})
        cooldown = 0 if testing_mode else database.paper_trade_cooldown_remaining(
            settings.get("paper_trade_cooldown_minutes", 15), checked_at
        )
        safety_settings = {
            **settings, "max_trades_per_day": adaptive_limit,
            "max_concurrent_paper_trades": max_open,
        }
        safety = assess_execution_safety(
            now=checked_at, candle_time=capture.get("candle_time"), quote=selected_quote, plan=plan,
            settings=safety_settings, progress=progress, cooldown_remaining=cooldown, event_risk=event_risk, expiry_day=expiry_day,
            recovery_assessment=OvertradingGuard().assess(settings, database, checked_at),
        )
        plan["execution_safety"] = safety
        plan["signal_timing"] = dict(timing)
        plan["evidence_context"] = {
            "candle_time": capture.get("candle_time"), "atr_14": capture.get("atr_14"),
            "volume": capture.get("volume"), "volume_ratio": capture.get("volume_ratio"),
            "volume_threshold": environment.get("volume_threshold"), "market_regime": environment.get("regime"),
            "zones": strategy.get("zones") or {}, "provider": provider,
            "provider_data_age_seconds": capture.get("provider_data_age_seconds"),
        }
        # Historical outcomes are advisory context only. They never bypass the
        # current candle's strategy, execution, event, expiry or risk gates.
        current_fingerprint = build_trade_fingerprint(
            {"symbol": symbol, "option_type": candidate, "ai_score": strategy.get("score", 0)}, plan
        )
        validation_fingerprint = "|".join((
            symbol, str(candidate), str(capture.get("candle_time") or ""),
            str(plan.get("contract", {}).get("strike") or ""), str(environment.get("regime") or "UNKNOWN"),
        ))
        plan["validation_fingerprint"] = validation_fingerprint
        fixed_cost = max(0.0, float(settings.get("paper_execution_fixed_cost", 40.0)))
        slip_points = max(0.0, float(settings.get("paper_execution_slippage_points", 0.25)))
        plan["estimated_round_trip_cost"] = round(fixed_cost + 2 * slip_points * int(plan["quantity"]), 2)
        if database.has_recent_paper_thesis(
            validation_fingerprint, int(settings.get("paper_unique_thesis_window_minutes", 15))
        ):
            reason = "Same symbol/side/candle/strike/regime thesis is already under validation"
            result = _attempt(
                "No new paper trade: duplicate market thesis is not counted as an independent accuracy sample.",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=[reason], chain=chain, timing=timing, outcome="SAFETY BLOCK",
                safety_blockers=[reason], warnings=["Existing trade monitoring continues"],
            )
            result["proposed_plan"] = plan
            return _record(database, symbol, result)
        plan["historical_outcome_matches"] = database.find_trade_outcome_analogs(current_fingerprint)
        if not safety["allowed"]:
            chart["warnings"].extend(safety["blockers"])
            result = _attempt(
                "No new paper trade: evidence passed, but operational hard-risk validation blocked execution.",
                checked_at, capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=safety["blockers"], chain=chain, timing=timing,
                outcome="SAFETY BLOCK", safety_blockers=safety["blockers"], warnings=safety["warnings"],
            )
            result["proposed_plan"] = plan
            return _record(database, symbol, result)
        # Approval belongs only to the completed candle that produced it. If a
        # new candle closes before capture, discard every stale tick and let the
        # next cycle calculate the checklist from the new market scenario.
        final_candles = _completed_candles(
            MarketDataHub.candles(client, future["exchange"], future["token"], "FIVE_MINUTE", 5, force=True),
            datetime.now(),
        )
        final_candle_time = str(final_candles[-1].get("time", "")) if final_candles else ""
        approved_candle_time = str(capture.get("candle_time", ""))
        if not final_candle_time or final_candle_time != approved_candle_time:
            reason = (
                f"Completed candle changed from {approved_candle_time or 'unavailable'} "
                f"to {final_candle_time or 'unavailable'}; stale checklist discarded"
            )
            chart["warnings"].append(reason)
            result = _attempt(
                "No new paper trade: candle/scenario changed before final capture; checklist will be recalculated.",
                datetime.now(), capture=capture, chart=chart, candidate=candidate, future=future,
                blockers=[reason], chain=chain, timing=timing,
                outcome="SAFETY BLOCK", safety_blockers=[reason],
            )
            result["proposed_plan"] = plan
            return _record(database, symbol, result)
        final_capture_at = datetime.now().isoformat(timespec="seconds")
        if not isinstance(timing, dict):
            timing = _fallback_timing("FIRST VALID", checked_at, capture.get("candle_time"))
        timing.update({"stage": "CAPTURED", "final_capture_at": final_capture_at})
        if timing.get("signal_discovery_at"):
            timing["delay_seconds"] = max(0, int((
                datetime.fromisoformat(final_capture_at) - datetime.fromisoformat(timing["signal_discovery_at"])
            ).total_seconds()))
        if timing.get("first_valid_at"):
            timing["entry_delay_seconds"] = max(0, int((
                datetime.fromisoformat(final_capture_at) - datetime.fromisoformat(timing["first_valid_at"])
            ).total_seconds()))
        plan["signal_timing"] = dict(timing)
        trade_id = database.save_paper_trade(plan)
        chart["signal_timing"] = timing
        result = _attempt("Paper trade captured", checked_at, capture=capture, chart=chart, candidate=candidate, future=future, chain=chain, timing=timing, outcome="CAPTURED")
        result.update({"trade_id": trade_id, "plan": plan, "capture": capture})
        return _record(database, symbol, result)
    finally:
        database.close()
