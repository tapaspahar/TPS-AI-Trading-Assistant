"""SQLite persistence for the TPS trade journal."""

from __future__ import annotations

import sqlite3
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from engine.tps_engine import TPSEngine
from models.trade import Trade


class Database:
    """Store and retrieve journal trades.

    ``db_path`` is injectable so tests and future deployments do not depend on
    the current working directory.
    """

    def __init__(self, db_path: str | Path | None = None):
        app_data = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TPS AI Trading Assistant"
        default_path = app_data / "tps_ai.db"
        self.db_path = Path(db_path) if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path is None and not self.db_path.exists():
            legacy_path = Path(__file__).resolve().parents[1] / "database" / "tps_ai.db"
            if legacy_path.exists() and legacy_path != self.db_path:
                shutil.copy2(legacy_path, self.db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA synchronous=NORMAL")
        self.cursor.execute("PRAGMA busy_timeout=5000")
        self.create_tables()

    def create_tables(self) -> None:
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS execution_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                trading_date TEXT NOT NULL, fingerprint TEXT NOT NULL, broker TEXT NOT NULL,
                exchange TEXT NOT NULL, symbol_token TEXT NOT NULL, trading_symbol TEXT NOT NULL,
                side TEXT NOT NULL, quantity INTEGER NOT NULL, limit_price REAL NOT NULL,
                status TEXT NOT NULL, broker_order_id TEXT, message TEXT, realized_pnl REAL DEFAULT 0
            )"""
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_audit_day ON execution_audit(trading_date)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_audit_fingerprint ON execution_audit(fingerprint, created_at)")
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS order_intelligence_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                broker_order_id TEXT NOT NULL,
                trading_symbol TEXT NOT NULL,
                order_status TEXT NOT NULL,
                analysis_state TEXT NOT NULL,
                market_price REAL,
                unrealized_points REAL,
                mfe_points REAL,
                mae_points REAL,
                details_json TEXT NOT NULL,
                UNIQUE(broker_order_id, captured_at)
            )"""
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_intelligence_day ON order_intelligence_snapshots(trading_date, captured_at DESC)"
        )
        execution_columns = {row["name"] for row in self.cursor.execute("PRAGMA table_info(execution_audit)")}
        for column, definition in {
            "average_fill_price": "REAL", "filled_quantity": "INTEGER",
            "estimated_charges": "REAL NOT NULL DEFAULT 0", "slippage_amount": "REAL",
            "last_reconciled_at": "TEXT",
        }.items():
            if column not in execution_columns:
                self.cursor.execute(f"ALTER TABLE execution_audit ADD COLUMN {column} {definition}")
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS execution_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, trading_date TEXT NOT NULL,
                source_page TEXT NOT NULL, mode TEXT NOT NULL, underlying TEXT NOT NULL,
                strike REAL NOT NULL, expiry TEXT NOT NULL, lots INTEGER NOT NULL,
                quantity INTEGER NOT NULL, status TEXT NOT NULL,
                ce_symbol TEXT NOT NULL, ce_token TEXT NOT NULL, ce_entry REAL NOT NULL,
                pe_symbol TEXT NOT NULL, pe_token TEXT NOT NULL, pe_entry REAL NOT NULL,
                ce_order_id TEXT, pe_order_id TEXT, target_pnl REAL NOT NULL,
                stop_pnl REAL NOT NULL, time_exit TEXT, last_pnl REAL DEFAULT 0,
                exit_reason TEXT, details_json TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_pairs_day ON execution_pairs(trading_date, status)")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                trade_time TEXT NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT,
                strike TEXT,
                option_type TEXT,
                entry REAL NOT NULL,
                exit REAL NOT NULL,
                stoploss REAL NOT NULL,
                target REAL NOT NULL,
                quantity INTEGER NOT NULL,
                pnl REAL NOT NULL,
                rr_ratio REAL NOT NULL,
                setup TEXT,
                trend INTEGER NOT NULL DEFAULT 0,
                vwap INTEGER NOT NULL DEFAULT 0,
                ema INTEGER NOT NULL DEFAULT 0,
                volume INTEGER NOT NULL DEFAULT 0,
                oi INTEGER NOT NULL DEFAULT 0,
                psychology_before TEXT,
                psychology_after TEXT,
                mistake TEXT,
                confidence INTEGER NOT NULL DEFAULT 0,
                ai_score INTEGER NOT NULL DEFAULT 0,
                ai_decision TEXT,
                ai_review TEXT,
                notes TEXT,
                screenshot TEXT,
                status TEXT NOT NULL DEFAULT 'CLOSED',
                outcome TEXT NOT NULL DEFAULT 'MANUAL EXIT',
                closed_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trade_links (
                trade_id INTEGER PRIMARY KEY,
                exchange TEXT NOT NULL,
                token TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                last_ltp REAL,
                min_ltp REAL,
                max_ltp REAL,
                last_alert_level TEXT,
                initial_stoploss REAL,
                trailing_stoploss REAL,
                plan_json TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                UNIQUE(trade_id, alert_type, status)
            )
            """
        )
        # Migrate journals created before open-trade tracking was introduced.
        columns = {row["name"] for row in self.cursor.execute("PRAGMA table_info(trades)")}
        if "status" not in columns:
            self.cursor.execute("ALTER TABLE trades ADD COLUMN status TEXT NOT NULL DEFAULT 'CLOSED'")
        if "outcome" not in columns:
            self.cursor.execute("ALTER TABLE trades ADD COLUMN outcome TEXT NOT NULL DEFAULT 'MANUAL EXIT'")
        if "closed_at" not in columns:
            self.cursor.execute("ALTER TABLE trades ADD COLUMN closed_at TEXT")
        paper_columns = {row["name"] for row in self.cursor.execute("PRAGMA table_info(paper_trade_links)")}
        for name, definition in (("last_ltp", "REAL"), ("min_ltp", "REAL"), ("max_ltp", "REAL"), ("last_alert_level", "TEXT"),
                                 ("initial_stoploss", "REAL"), ("trailing_stoploss", "REAL"), ("plan_json", "TEXT"),
                                 ("entry_lateness_seconds", "INTEGER"), ("premium_spread_percent", "REAL"),
                                 ("initial_atr", "REAL"), ("mae", "REAL"), ("mfe", "REAL")):
            if name not in paper_columns:
                self.cursor.execute(f"ALTER TABLE paper_trade_links ADD COLUMN {name} {definition}")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL,
                volume_ema REAL,
                ema_5 REAL,
                ema_20 REAL,
                ema_50 REAL,
                vwap REAL,
                supertrend REAL,
                rsi_14 REAL,
                atr_14 REAL,
                oi_pcr REAL,
                volume_pcr REAL,
                oi_pcr_change REAL,
                volume_pcr_change REAL,
                put_support REAL,
                call_resistance REAL,
                option_contracts INTEGER,
                UNIQUE(captured_at, symbol, timeframe)
            )
            """
        )
        snapshot_columns = {row["name"] for row in self.cursor.execute("PRAGMA table_info(market_snapshots)")}
        if "oi_pcr_change" not in snapshot_columns:
            self.cursor.execute("ALTER TABLE market_snapshots ADD COLUMN oi_pcr_change REAL")
        if "volume_pcr_change" not in snapshot_columns:
            self.cursor.execute("ALTER TABLE market_snapshots ADD COLUMN volume_pcr_change REAL")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_trend_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                trend TEXT NOT NULL,
                chart_pattern TEXT NOT NULL,
                candle_signature TEXT NOT NULL,
                session_open REAL NOT NULL,
                session_high REAL NOT NULL,
                session_low REAL NOT NULL,
                session_close REAL NOT NULL,
                return_pct REAL NOT NULL,
                range_pct REAL NOT NULL,
                snapshot_count INTEGER NOT NULL,
                outcome_text TEXT NOT NULL,
                features_json TEXT NOT NULL,
                UNIQUE(trade_date, symbol)
            )
            """
        )
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS index_candle_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL, candle_time TEXT NOT NULL, analyzed_at TEXT NOT NULL,
                symbol TEXT NOT NULL, state TEXT NOT NULL, direction TEXT NOT NULL,
                aggression TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL,
                move_points REAL, range_points REAL, range_ratio REAL, volume REAL, volume_ratio REAL,
                oi_direction TEXT, oi_quality INTEGER, call_oi REAL, put_oi REAL,
                call_coi REAL, put_coi REAL, put_wall REAL, put_wall_health TEXT,
                call_wall REAL, call_wall_health TEXT, source_completeness INTEGER,
                explanation TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(symbol, candle_time)
            )"""
        )
        index_memory_columns = {row["name"] for row in self.cursor.execute("PRAGMA table_info(index_candle_analyses)")}
        for column in ("atm_strike", "atm_ce_premium", "atm_pe_premium", "oi_pcr", "volume_pcr"):
            if column not in index_memory_columns:
                self.cursor.execute(f"ALTER TABLE index_candle_analyses ADD COLUMN {column} REAL")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_index_candle_day ON index_candle_analyses(trade_date, candle_time)")
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS index_daily_analyses (
                trade_date TEXT PRIMARY KEY, generated_at TEXT NOT NULL,
                market_state TEXT NOT NULL, source_completeness INTEGER NOT NULL,
                summary_text TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                candle_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT,
                strategy_name TEXT NOT NULL,
                family TEXT NOT NULL,
                bias TEXT NOT NULL,
                structure_key TEXT NOT NULL,
                legs_json TEXT NOT NULL,
                entry_spot REAL NOT NULL,
                last_spot REAL NOT NULL,
                max_profit REAL NOT NULL,
                max_loss REAL NOT NULL,
                breakevens_json TEXT NOT NULL,
                profit_zone TEXT NOT NULL,
                scenario_win_rate REAL NOT NULL,
                rank_score REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                outcome TEXT NOT NULL DEFAULT 'MONITORING',
                current_pnl REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                exit_at TEXT,
                explanation TEXT NOT NULL,
                result_review TEXT,
                source_json TEXT NOT NULL,
                UNIQUE(symbol, candle_time, structure_key)
            )
            """
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_trades_date ON strategy_trades(trade_date DESC, id DESC)")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_session_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                market_direction TEXT NOT NULL,
                market_regime TEXT NOT NULL,
                total_strategies INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                flat INTEGER NOT NULL DEFAULT 0,
                best_strategy TEXT,
                best_pnl REAL NOT NULL DEFAULT 0,
                worst_strategy TEXT,
                worst_pnl REAL NOT NULL DEFAULT 0,
                review_text TEXT NOT NULL,
                UNIQUE(trade_date, symbol)
            )
            """
        )
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_reviews_date ON strategy_session_reviews(trade_date DESC, id DESC)")
        strategy_columns = {
            row["name"] for row in self.cursor.execute("PRAGMA table_info(strategy_trades)")
        }
        for column, definition in {
            "friendly_name": "TEXT",
            "capital_required": "REAL NOT NULL DEFAULT 0",
            "entry_cashflow": "REAL NOT NULL DEFAULT 0",
            "return_on_capital": "REAL NOT NULL DEFAULT 0",
            "market_regime": "TEXT",
            "target_profit_amount": "REAL NOT NULL DEFAULT 0",
            "stop_loss_amount": "REAL NOT NULL DEFAULT 0",
        }.items():
            if column not in strategy_columns:
                self.cursor.execute(f"ALTER TABLE strategy_trades ADD COLUMN {column} {definition}")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_outcome_reviews (
                trade_id INTEGER PRIMARY KEY,
                generated_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                fingerprint_json TEXT NOT NULL,
                review_text TEXT NOT NULL,
                solution_text TEXT NOT NULL,
                mfe REAL NOT NULL DEFAULT 0,
                mae REAL NOT NULL DEFAULT 0,
                pnl REAL NOT NULL DEFAULT 0
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_trade_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checked_at TEXT NOT NULL,
                candle_time TEXT,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                future_symbol TEXT,
                outcome TEXT NOT NULL,
                decision TEXT,
                candidate TEXT,
                confirmations_passed INTEGER,
                confirmations_total INTEGER,
                score INTEGER,
                trade_id INTEGER,
                status_text TEXT NOT NULL,
                details_json TEXT NOT NULL,
                UNIQUE(symbol, candle_time)
            )
            """
        )
        attempt_columns = {
            row["name"] for row in self.cursor.execute("PRAGMA table_info(auto_trade_attempts)")
        }
        for column, definition in {
            "signal_discovered_at": "TEXT",
            "first_valid_trigger_at": "TEXT",
            "final_capture_at": "TEXT",
            "timing_delay_seconds": "INTEGER",
            "timing_stage": "TEXT",
            "volume_reason_code": "TEXT",
            "chart_support": "REAL",
            "chart_resistance": "REAL",
            "oi_support": "REAL",
            "oi_resistance": "REAL",
            "level_confluence": "TEXT",
            "level_distance_atr": "REAL",
            "level_age_seconds": "INTEGER",
            "provider": "TEXT",
            "provider_data_age_seconds": "INTEGER",
            "primary_blocker": "TEXT",
            "secondary_warnings_json": "TEXT NOT NULL DEFAULT '[]'",
            "evidence_states_json": "TEXT NOT NULL DEFAULT '{}'",
            "source_completeness_json": "TEXT NOT NULL DEFAULT '{}'",
        }.items():
            if column not in attempt_columns:
                self.cursor.execute(f"ALTER TABLE auto_trade_attempts ADD COLUMN {column} {definition}")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS post_market_tps_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                metrics_json TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pcr_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                call_oi REAL NOT NULL,
                put_oi REAL NOT NULL,
                pcr_oi REAL,
                call_volume REAL NOT NULL,
                put_volume REAL NOT NULL,
                pcr_volume REAL,
                call_oi_change REAL,
                put_oi_change REAL,
                sentiment TEXT NOT NULL,
                confidence INTEGER NOT NULL
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pcr_symbol_expiry_time ON pcr_observations(symbol, expiry, captured_at DESC)"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gap_probability_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forecast_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                stage TEXT NOT NULL,
                predicted_class TEXT NOT NULL,
                gap_up_probability REAL NOT NULL,
                flat_probability REAL NOT NULL,
                gap_down_probability REAL NOT NULL,
                confidence INTEGER NOT NULL,
                data_quality INTEGER NOT NULL,
                prior_close REAL NOT NULL,
                inputs_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                actual_open REAL,
                actual_gap_percent REAL,
                actual_class TEXT,
                correct INTEGER,
                UNIQUE(forecast_date, symbol, stage)
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gap_forecast_symbol_date ON gap_probability_forecasts(symbol, forecast_date DESC)"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                candle_time TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                instrument TEXT,
                action TEXT NOT NULL,
                state TEXT NOT NULL,
                score REAL NOT NULL,
                entry REAL,
                stop REAL,
                target_1 REAL,
                target_2 REAL,
                quantity INTEGER,
                rr_ratio REAL,
                exit_rule TEXT NOT NULL,
                details_json TEXT NOT NULL,
                UNIQUE(candle_time, market_type, symbol)
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_auto_opportunity_time ON auto_opportunities(scanned_at DESC, id DESC)"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(created_at DESC, id DESC)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read, created_at DESC)"
        )
        notification_columns = {
            row["name"] for row in self.cursor.execute("PRAGMA table_info(notifications)")
        }
        if "event_key" not in notification_columns:
            self.cursor.execute("ALTER TABLE notifications ADD COLUMN event_key TEXT")
        self.cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_event_key "
            "ON notifications(event_key) WHERE event_key IS NOT NULL"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS self_development_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                source_generated_at TEXT NOT NULL,
                health_score INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                suggestions_json TEXT NOT NULL
            )
            """
        )
        review_columns = {
            row["name"] for row in self.cursor.execute("PRAGMA table_info(self_development_reviews)")
        }
        for column, definition in {
            "review_state": "TEXT NOT NULL DEFAULT 'DRAFT'",
            "revision": "INTEGER NOT NULL DEFAULT 1",
            "feature_version": "TEXT",
            "build_id": "TEXT",
            "source_fingerprint": "TEXT",
            "finalized_at": "TEXT",
        }.items():
            if column not in review_columns:
                self.cursor.execute(f"ALTER TABLE self_development_reviews ADD COLUMN {column} {definition}")
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS self_development_review_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                revision INTEGER NOT NULL,
                saved_at TEXT NOT NULL,
                review_state TEXT NOT NULL,
                source_fingerprint TEXT,
                snapshot_json TEXT NOT NULL,
                UNIQUE(review_id, revision)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS development_feature_evidence (
                feature_key TEXT PRIMARY KEY,
                feature_version TEXT NOT NULL,
                build_id TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL,
                replay_passed_at TEXT,
                paper_forward_passed_at TEXT,
                approved_at TEXT,
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                candle_time TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                status TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                details_json TEXT NOT NULL,
                UNIQUE(symbol, candle_time)
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_evaluation_slots_date ON evaluation_slots(trade_date, symbol, candle_time)"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_request_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                operation TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                cache_hit INTEGER NOT NULL DEFAULT 0,
                data_timestamp TEXT,
                data_age_seconds INTEGER,
                error_code TEXT,
                details_json TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_broker_telemetry_time ON broker_request_telemetry(provider, completed_at DESC)"
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS counterfactual_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                current_score INTEGER NOT NULL,
                proposed_score INTEGER NOT NULL,
                current_matches INTEGER NOT NULL,
                proposed_matches INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                UNIQUE(trade_date, proposed_score, proposed_matches)
            )
            """
        )
        self.cursor.execute(
            """UPDATE auto_trade_attempts SET outcome = CASE outcome
                   WHEN 'TRADE CAPTURED' THEN 'CAPTURED'
                   WHEN 'NO TRADE' THEN 'STRATEGY REJECT'
                   WHEN 'RETRY PENDING' THEN 'DATA GAP'
                   WHEN 'SKIPPED' THEN 'DATA GAP'
                   ELSE outcome END"""
        )
        # Repair legacy WATCH rows that were labelled CANDIDATE merely because
        # a CE/PE side existed.  Preserve genuine qualified candidates and all
        # captured/safety/data-gap history.
        for legacy_row in self.cursor.execute(
            "SELECT id, details_json FROM auto_trade_attempts WHERE outcome = 'CANDIDATE' AND trade_id IS NULL"
        ).fetchall():
            try:
                legacy_details = json.loads(legacy_row["details_json"] or "{}")
                legacy_chart = (legacy_details.get("attempt") or {}).get("chart") or {}
                legacy_strategy = legacy_chart.get("strategy") or {}
                strategy_qualified = bool(legacy_chart.get("trade_ready") or legacy_strategy.get("trade_ready"))
            except (TypeError, ValueError, json.JSONDecodeError):
                strategy_qualified = True  # Never rewrite history we cannot prove was misclassified.
            if not strategy_qualified:
                self.cursor.execute(
                    "UPDATE auto_trade_attempts SET outcome = 'STRATEGY REJECT' WHERE id = ?",
                    (int(legacy_row["id"]),),
                )
        self._backfill_attempt_evidence_states()
        self.connection.commit()

        # Upgrade-safe backfill: previously closed automatic paper trades also
        # become searchable outcome memories without changing their records.
        for legacy_trade in self.cursor.execute(
            """SELECT t.id FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id
               LEFT JOIN trade_outcome_reviews r ON r.trade_id=t.id
               WHERE t.status='CLOSED' AND r.trade_id IS NULL"""
        ).fetchall():
            self._save_automatic_outcome_review(int(legacy_trade["id"]))
        self.connection.commit()

    def create_execution_audit(self, order, fingerprint, status, message=""):
        now = datetime.now().astimezone()
        result = self.cursor.execute(
            """INSERT INTO execution_audit
            (created_at,trading_date,fingerprint,broker,exchange,symbol_token,trading_symbol,side,quantity,limit_price,status,message)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now.isoformat(timespec="seconds"), now.date().isoformat(), fingerprint, "angel_one",
             order["exchange"], str(order["symbol_token"]), order["trading_symbol"], order["side"],
             int(order["quantity"]), float(order["limit_price"]), status, message),
        )
        self.connection.commit()
        return int(result.lastrowid)

    def update_execution_audit(self, audit_id, status, broker_order_id="", message=""):
        self.cursor.execute(
            "UPDATE execution_audit SET status=?, broker_order_id=?, message=? WHERE id=?",
            (status, broker_order_id, message, int(audit_id)),
        )
        self.connection.commit()

    def update_execution_fill(self, audit_id: int, *, status: str, average_fill_price=None,
                              filled_quantity=None, estimated_charges=0.0, message=""):
        row = self.get_execution_audit(audit_id)
        requested = float(row["limit_price"] or 0) if row else 0.0
        filled = float(average_fill_price or 0)
        quantity = int(filled_quantity or (row["quantity"] if row else 0) or 0)
        side = str(row["side"] or "BUY").upper() if row else "BUY"
        adverse_points = (filled - requested) if side == "BUY" else (requested - filled)
        slippage = adverse_points * quantity if filled > 0 and requested > 0 else None
        self.cursor.execute(
            """UPDATE execution_audit SET status=?, average_fill_price=?, filled_quantity=?,
                      estimated_charges=?, slippage_amount=?, last_reconciled_at=?, message=? WHERE id=?""",
            (str(status), average_fill_price, quantity, float(estimated_charges or 0), slippage,
             datetime.now().astimezone().isoformat(timespec="seconds"), str(message or ""), int(audit_id)),
        )
        self.connection.commit()

    def get_execution_audit(self, audit_id):
        return self.cursor.execute("SELECT * FROM execution_audit WHERE id=?", (int(audit_id),)).fetchone()

    def get_pending_execution_audits(self):
        return self.cursor.execute(
            """SELECT * FROM execution_audit
               WHERE status IN ('SUBMITTING','SUBMISSION_UNKNOWN','ACCEPTED_NOT_FILLED','OPEN','PARTIAL','PENDING')
               ORDER BY id"""
        ).fetchall()

    def save_order_intelligence_snapshot(self, snapshot: dict) -> int:
        self.cursor.execute(
            """INSERT OR REPLACE INTO order_intelligence_snapshots
               (captured_at,trading_date,broker_order_id,trading_symbol,order_status,analysis_state,
                market_price,unrealized_points,mfe_points,mae_points,details_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                snapshot["captured_at"], snapshot["trading_date"], snapshot["broker_order_id"],
                snapshot["trading_symbol"], snapshot["order_status"], snapshot["analysis_state"],
                snapshot.get("market_price"), snapshot.get("unrealized_points"), snapshot.get("mfe_points"),
                snapshot.get("mae_points"), json.dumps(snapshot, ensure_ascii=False, default=str),
            ),
        )
        self.connection.commit()
        return int(self.cursor.lastrowid)

    def get_order_intelligence_snapshots(self, trading_date: str | None = None, limit: int = 1000):
        if trading_date:
            return self.cursor.execute(
                "SELECT * FROM order_intelligence_snapshots WHERE trading_date=? ORDER BY captured_at DESC LIMIT ?",
                (trading_date, max(1, min(int(limit), 5000))),
            ).fetchall()
        return self.cursor.execute(
            "SELECT * FROM order_intelligence_snapshots ORDER BY captured_at DESC LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()

    def count_execution_orders(self, trading_date):
        row = self.cursor.execute(
            "SELECT COUNT(*) n FROM execution_audit WHERE trading_date=? AND status NOT IN ('BLOCKED','REJECTED','PAPER_PLAN')",
            (trading_date,),
        ).fetchone()
        return int(row["n"])

    def execution_loss_today(self, trading_date):
        row = self.cursor.execute(
            "SELECT COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN -realized_pnl ELSE 0 END),0) n FROM execution_audit WHERE trading_date=?",
            (trading_date,),
        ).fetchone()
        return float(row["n"])

    def has_recent_execution_fingerprint(self, fingerprint, seconds):
        cutoff = (datetime.now().astimezone() - timedelta(seconds=int(seconds))).isoformat(timespec="seconds")
        row = self.cursor.execute(
            "SELECT 1 FROM execution_audit WHERE fingerprint=? AND created_at>=? AND status NOT IN ('BLOCKED','REJECTED','PAPER_PLAN') LIMIT 1",
            (fingerprint, cutoff),
        ).fetchone()
        return bool(row)

    def create_execution_pair(self, pair):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        result = self.cursor.execute(
            """INSERT INTO execution_pairs
            (created_at,updated_at,trading_date,source_page,mode,underlying,strike,expiry,lots,quantity,status,
             ce_symbol,ce_token,ce_entry,pe_symbol,pe_token,pe_entry,target_pnl,stop_pnl,time_exit,details_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, now, pair["trading_date"], pair["source_page"], pair["mode"], pair["underlying"],
             float(pair["strike"]), pair["expiry"], int(pair["lots"]), int(pair["quantity"]), pair["status"],
             pair["ce_symbol"], str(pair["ce_token"]), float(pair["ce_entry"]), pair["pe_symbol"],
             str(pair["pe_token"]), float(pair["pe_entry"]), float(pair["target_pnl"]),
             float(pair["stop_pnl"]), pair.get("time_exit", ""), json.dumps(pair.get("details") or {})),
        )
        self.connection.commit()
        return int(result.lastrowid)

    def update_execution_pair(self, pair_id, **values):
        allowed = {"status", "ce_order_id", "pe_order_id", "last_pnl", "exit_reason", "details_json"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        sql = ",".join(f"{key}=?" for key in updates)
        self.cursor.execute(f"UPDATE execution_pairs SET {sql} WHERE id=?", (*updates.values(), int(pair_id)))
        self.connection.commit()

    def get_open_execution_pair(self, underlying=None):
        sql = "SELECT * FROM execution_pairs WHERE status IN ('PAPER_OPEN','REAL_SUBMITTING','REAL_OPEN','EXITING')"
        params = []
        if underlying:
            sql += " AND underlying=?"; params.append(str(underlying))
        sql += " ORDER BY id DESC LIMIT 1"
        return self.cursor.execute(sql, params).fetchone()

    def has_execution_pair(self, trading_date, source_page, underlying, strike):
        """Return whether this exact dated strategy trigger was already recorded.

        Closed and failed rows intentionally count: an automatic multi-leg trigger
        must never be silently resubmitted after an app restart or broker error.
        """
        row = self.cursor.execute(
            """SELECT 1 FROM execution_pairs
               WHERE trading_date=? AND source_page=? AND underlying=? AND strike=?
               LIMIT 1""",
            (str(trading_date), str(source_page), str(underlying), float(strike)),
        ).fetchone()
        return bool(row)

    def _backfill_attempt_evidence_states(self) -> int:
        """Recover structured evidence already present in legacy payloads.

        Older builds saved the complete strategy inside ``details_json`` but
        left the indexed evidence column empty. This copies recorded facts;
        it never reconstructs or guesses market evidence.
        """
        updated = 0
        rows = self.cursor.execute(
            """SELECT id, details_json FROM auto_trade_attempts
               WHERE evidence_states_json IS NULL OR evidence_states_json = '' OR evidence_states_json = '{}'"""
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["details_json"] or "{}")
                attempt_payload = payload.get("attempt") or {}
                chart_payload = attempt_payload.get("chart") or {}
                strategy_payload = chart_payload.get("strategy") or {}
                states = (
                    chart_payload.get("evidence_states")
                    or strategy_payload.get("evidence_states")
                    or attempt_payload.get("evidence_states")
                    or {}
                )
                if not isinstance(states, dict) or not states:
                    continue
                gaps = (
                    attempt_payload.get("data_gaps")
                    or chart_payload.get("data_gaps")
                    or strategy_payload.get("data_gaps")
                    or []
                )
                known = sum(str(value).upper() != "UNKNOWN" for value in states.values())
                completeness = {
                    "complete": not bool(gaps) and known == len(states),
                    "data_gaps": gaps,
                    "total": len(states),
                    "known": known,
                }
                self.cursor.execute(
                    """UPDATE auto_trade_attempts
                       SET evidence_states_json = ?, source_completeness_json = ? WHERE id = ?""",
                    (
                        json.dumps(states, ensure_ascii=False, default=str),
                        json.dumps(completeness, ensure_ascii=False, default=str),
                        int(row["id"]),
                    ),
                )
                updated += 1
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return updated

    def save_self_development_review(self, review: dict) -> int:
        """Save one date-wise rectification review while retaining review states."""
        existing = self.get_self_development_review(str(review["trade_date"]))
        previous_states = {}
        if existing:
            try:
                previous_states = {
                    str(item.get("key")): str(item.get("status") or "OPEN")
                    for item in json.loads(existing["suggestions_json"] or "[]")
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                previous_states = {}
        suggestions = []
        for item in review.get("suggestions") or []:
            value = dict(item)
            value["status"] = previous_states.get(str(value.get("key")), str(value.get("status") or "OPEN"))
            suggestions.append(value)
        # The post-market report generation timestamp is the immutable source
        # revision. Human review statuses and lifecycle labels must never create
        # a false market-evidence revision on refresh.
        source_fingerprint = str(review.get("source_fingerprint") or hashlib.sha256(
            str(review.get("source_generated_at")).encode("utf-8")
        ).hexdigest())
        source_changed = existing is None or str(existing["source_fingerprint"] or "") != source_fingerprint
        next_revision = (int(existing["revision"] or 1) + 1) if existing and source_changed else (int(existing["revision"] or 1) if existing else 1)
        review_state = "DRAFT" if source_changed else str(existing["review_state"] or "DRAFT")
        self.cursor.execute(
            """
            INSERT INTO self_development_reviews
                (trade_date, generated_at, source_generated_at, health_score, verdict, summary_text,
                 suggestions_json, review_state, revision, feature_version, build_id, source_fingerprint, finalized_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date) DO UPDATE SET
                generated_at=excluded.generated_at,
                source_generated_at=excluded.source_generated_at,
                health_score=excluded.health_score,
                verdict=excluded.verdict,
                summary_text=excluded.summary_text,
                suggestions_json=excluded.suggestions_json,
                review_state=excluded.review_state,
                revision=excluded.revision,
                feature_version=excluded.feature_version,
                build_id=excluded.build_id,
                source_fingerprint=excluded.source_fingerprint,
                finalized_at=CASE WHEN excluded.review_state = 'FINAL' THEN self_development_reviews.finalized_at ELSE NULL END
            """,
            (
                review["trade_date"], review["generated_at"], review["source_generated_at"],
                int(review["health_score"]), review["verdict"], review["summary_text"],
                json.dumps(suggestions, ensure_ascii=False, default=str),
                review_state, next_revision, review.get("feature_version"), review.get("build_id"),
                source_fingerprint, existing["finalized_at"] if existing and review_state == "FINAL" else None,
            ),
        )
        row = self.get_self_development_review(str(review["trade_date"]))
        snapshot = dict(review)
        snapshot.update({"suggestions": suggestions, "review_state": review_state, "revision": next_revision})
        self.cursor.execute(
            """INSERT OR REPLACE INTO self_development_review_revisions
               (review_id, trade_date, revision, saved_at, review_state, source_fingerprint, snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (int(row["id"]), review["trade_date"], next_revision, datetime.now().astimezone().isoformat(timespec="seconds"),
             review_state, source_fingerprint, json.dumps(snapshot, ensure_ascii=False, default=str)),
        )
        self.connection.commit()
        return int(row["id"])

    def finalize_self_development_review(self, trade_date: str) -> bool:
        finalized_at = datetime.now().astimezone().isoformat(timespec="seconds")
        result = self.cursor.execute(
            "UPDATE self_development_reviews SET review_state = 'FINAL', finalized_at = ? WHERE trade_date = ?",
            (finalized_at, trade_date),
        )
        self.connection.commit()
        return result.rowcount == 1

    def get_self_development_review_revisions(self, trade_date: str) -> list[sqlite3.Row]:
        return self.cursor.execute(
            "SELECT * FROM self_development_review_revisions WHERE trade_date = ? ORDER BY revision DESC", (trade_date,)
        ).fetchall()

    def save_development_feature_evidence(self, feature: dict) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.cursor.execute(
            """INSERT INTO development_feature_evidence
               (feature_key, feature_version, build_id, lifecycle_state, replay_passed_at,
                paper_forward_passed_at, approved_at, evidence_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(feature_key) DO UPDATE SET
                 feature_version=excluded.feature_version, build_id=excluded.build_id,
                 lifecycle_state=excluded.lifecycle_state, replay_passed_at=excluded.replay_passed_at,
                 paper_forward_passed_at=excluded.paper_forward_passed_at, approved_at=excluded.approved_at,
                 evidence_json=excluded.evidence_json, updated_at=excluded.updated_at""",
            (feature["feature_key"], feature["feature_version"], feature["build_id"], feature["lifecycle_state"],
             feature.get("replay_passed_at"), feature.get("paper_forward_passed_at"), feature.get("approved_at"),
             json.dumps(feature.get("evidence") or {}, ensure_ascii=False, default=str), now),
        )
        self.connection.commit()

    def get_development_feature_evidence(self) -> dict[str, sqlite3.Row]:
        return {str(row["feature_key"]): row for row in self.cursor.execute("SELECT * FROM development_feature_evidence").fetchall()}

    def get_self_development_review(self, trade_date: str) -> sqlite3.Row | None:
        return self.cursor.execute(
            "SELECT * FROM self_development_reviews WHERE trade_date = ?", (trade_date,)
        ).fetchone()

    def get_self_development_reviews(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.cursor.execute(
            """SELECT * FROM self_development_reviews
               ORDER BY substr(trade_date, 7, 4) || substr(trade_date, 4, 2) || substr(trade_date, 1, 2) DESC
               LIMIT ?""",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()

    def update_self_development_suggestion_status(
        self, trade_date: str, suggestion_key: str, status: str
    ) -> bool:
        row = self.get_self_development_review(trade_date)
        if not row:
            return False
        try:
            suggestions = json.loads(row["suggestions_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        changed = False
        for item in suggestions:
            if str(item.get("key")) == str(suggestion_key):
                item["status"] = "REVIEWED" if str(status).upper() == "REVIEWED" else "OPEN"
                changed = True
                break
        if changed:
            self.cursor.execute(
                "UPDATE self_development_reviews SET suggestions_json = ? WHERE trade_date = ?",
                (json.dumps(suggestions, ensure_ascii=False, default=str), trade_date),
            )
            self.connection.commit()
        return changed

    def save_evaluation_slot(
        self, symbol: str, scheduled_at: str, candle_time: str, status: str,
        reason_code: str, details: dict | None = None, heartbeat_at: str | None = None,
    ) -> int:
        """Persist one expected completed-candle slot without inventing a market evaluation."""
        heartbeat = heartbeat_at or datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            trade_date = datetime.fromisoformat(str(candle_time)).strftime("%d-%m-%Y")
        except ValueError:
            trade_date = datetime.now().strftime("%d-%m-%Y")
        self.cursor.execute(
            """
            INSERT INTO evaluation_slots
                (trade_date, symbol, scheduled_at, candle_time, heartbeat_at, status, reason_code, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, candle_time) DO UPDATE SET
                scheduled_at=excluded.scheduled_at,
                heartbeat_at=excluded.heartbeat_at,
                status=CASE
                    WHEN evaluation_slots.status = 'EVALUATED' THEN evaluation_slots.status
                    WHEN excluded.status = 'EVALUATED' THEN excluded.status
                    ELSE excluded.status END,
                reason_code=CASE
                    WHEN evaluation_slots.status = 'EVALUATED' THEN evaluation_slots.reason_code
                    WHEN excluded.status = 'EVALUATED' THEN excluded.reason_code
                    ELSE excluded.reason_code END,
                details_json=excluded.details_json
            """,
            (
                trade_date, str(symbol).upper(), str(scheduled_at), str(candle_time), heartbeat,
                str(status).upper(), str(reason_code).upper(),
                json.dumps(details or {}, ensure_ascii=False, default=str),
            ),
        )
        self.connection.commit()
        row = self.cursor.execute(
            "SELECT id FROM evaluation_slots WHERE symbol = ? AND candle_time = ?",
            (str(symbol).upper(), str(candle_time)),
        ).fetchone()
        return int(row["id"])

    def reconcile_evaluation_slots(
        self, symbol: str, now: datetime, *, enabled: bool, connected: bool
    ) -> int:
        """Backfill today's missing slot audit with explicit non-signal reason codes."""
        if now.weekday() >= 5:
            return 0
        from core.market_session import parse_session_times
        _pre_open, market_open, market_close = parse_session_times()
        first_completed = (datetime.combine(now.date(), market_open) + timedelta(minutes=5)).time()
        market_start = now.replace(hour=first_completed.hour, minute=first_completed.minute, second=0, microsecond=0)
        market_end = now.replace(hour=market_close.hour, minute=market_close.minute, second=0, microsecond=0)
        end = min(now.replace(second=0, microsecond=0), market_end)
        if end < market_start:
            return 0
        existing = {
            str(row["candle_time"])
            for row in self.cursor.execute(
                "SELECT candle_time FROM evaluation_slots WHERE trade_date = ? AND symbol = ?",
                (now.strftime("%d-%m-%Y"), str(symbol).upper()),
            ).fetchall()
        }
        attempts = {
            str(row["candle_time"])
            for row in self.cursor.execute(
                "SELECT candle_time FROM auto_trade_attempts WHERE trade_date = ? AND symbol = ? AND candle_time IS NOT NULL",
                (now.strftime("%d-%m-%Y"), str(symbol).upper()),
            ).fetchall()
        }
        reason = "AUTO_MODE_DISABLED" if not enabled else "BROKER_DISCONNECTED" if not connected else "MISSED_SLOT_BACKFILL"
        count = 0
        scheduled = market_start
        while scheduled <= end:
            candle = scheduled - timedelta(minutes=5)
            candle_key = candle.astimezone().isoformat(timespec="seconds") if candle.tzinfo else candle.isoformat(timespec="seconds")
            if candle_key not in existing:
                evaluated = any(value.startswith(candle.strftime("%Y-%m-%dT%H:%M")) for value in attempts)
                self.save_evaluation_slot(
                    symbol, scheduled.isoformat(timespec="seconds"), candle_key,
                    "EVALUATED" if evaluated else "GAP", "ATTEMPT_SAVED" if evaluated else reason,
                    {"backfilled": True, "auto_mode_enabled": enabled, "broker_connected": connected},
                )
                count += 1
            scheduled += timedelta(minutes=5)
        return count

    def get_evaluation_health(self, trade_date: str, symbol: str | None = "NIFTY") -> dict:
        if symbol and str(symbol).upper() != "ALL":
            rows = self.cursor.execute(
                "SELECT * FROM evaluation_slots WHERE trade_date = ? AND symbol = ? ORDER BY candle_time",
                (trade_date, str(symbol).upper()),
            ).fetchall()
            label = str(symbol).upper()
        else:
            rows = self.cursor.execute(
                "SELECT * FROM evaluation_slots WHERE trade_date = ? ORDER BY symbol, candle_time",
                (trade_date,),
            ).fetchall()
            label = "ALL"
        counts = Counter(str(row["status"]) for row in rows)
        reasons = Counter(str(row["reason_code"]) for row in rows if str(row["status"]) != "EVALUATED")
        total = len(rows)
        evaluated = int(counts.get("EVALUATED", 0))
        return {
            "trade_date": trade_date, "symbol": label, "expected_slots": total,
            "evaluated_slots": evaluated, "gap_slots": total - evaluated,
            "coverage_percent": round(evaluated * 100 / total, 1) if total else 0.0,
            "gap_reasons": dict(reasons), "rows": rows,
        }

    def save_broker_telemetry(self, event: dict) -> int:
        self.cursor.execute(
            """INSERT INTO broker_request_telemetry
               (provider, operation, started_at, completed_at, duration_ms, outcome, attempt_count,
                cache_hit, data_timestamp, data_age_seconds, error_code, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(event.get("provider") or "Broker"), str(event.get("operation") or "unknown"),
                str(event.get("started_at")), str(event.get("completed_at")),
                int(event.get("duration_ms") or 0), str(event.get("outcome") or "UNKNOWN").upper(),
                int(event.get("attempt_count") or 1), int(bool(event.get("cache_hit"))),
                event.get("data_timestamp"), event.get("data_age_seconds"), event.get("error_code"),
                json.dumps(event.get("details") or {}, ensure_ascii=False, default=str),
            ),
        )
        self.connection.commit()
        return int(self.cursor.lastrowid)

    def get_broker_health(self, provider: str | None = None, limit: int = 500) -> dict:
        where, values = "", []
        if provider:
            where, values = "WHERE provider = ?", [provider]
        rows = self.cursor.execute(
            f"SELECT * FROM broker_request_telemetry {where} ORDER BY id DESC LIMIT ?",
            (*values, max(1, min(int(limit), 5000))),
        ).fetchall()
        failures = sum(str(row["outcome"]) != "SUCCESS" for row in rows)
        last_good = next((row for row in rows if str(row["outcome"]) == "SUCCESS"), None)
        return {
            "requests": len(rows), "failures": failures,
            "success_rate": round((len(rows) - failures) * 100 / len(rows), 1) if rows else 0.0,
            "last_good_at": last_good["completed_at"] if last_good else None,
            "last_good_data_age_seconds": last_good["data_age_seconds"] if last_good else None,
            "providers": dict(Counter(str(row["provider"]) for row in rows)), "rows": rows,
        }

    def save_counterfactual_review(self, review: dict) -> int:
        self.cursor.execute(
            """INSERT INTO counterfactual_reviews
               (trade_date, generated_at, current_score, proposed_score, current_matches, proposed_matches, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date, proposed_score, proposed_matches) DO UPDATE SET
                   generated_at=excluded.generated_at, current_score=excluded.current_score,
                   current_matches=excluded.current_matches, result_json=excluded.result_json""",
            (
                review["trade_date"], review["generated_at"], int(review["current_score"]),
                int(review["proposed_score"]), int(review["current_matches"]),
                int(review["proposed_matches"]), json.dumps(review, ensure_ascii=False, default=str),
            ),
        )
        self.connection.commit()
        row = self.cursor.execute(
            "SELECT id FROM counterfactual_reviews WHERE trade_date=? AND proposed_score=? AND proposed_matches=?",
            (review["trade_date"], int(review["proposed_score"]), int(review["proposed_matches"])),
        ).fetchone()
        return int(row["id"])

    def get_counterfactual_reviews(self, trade_date: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        if trade_date:
            return self.cursor.execute(
                "SELECT * FROM counterfactual_reviews WHERE trade_date=? ORDER BY generated_at DESC LIMIT ?",
                (trade_date, max(1, min(int(limit), 1000))),
            ).fetchall()
        return self.cursor.execute(
            "SELECT * FROM counterfactual_reviews ORDER BY generated_at DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()

    def save_notification(
        self, category: str, title: str, message: str, created_at: str | None = None,
        event_key: str | None = None,
    ) -> int:
        """Persist one desktop alert so its history survives application updates."""
        timestamp = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
        result = self.cursor.execute(
            "INSERT OR IGNORE INTO notifications (created_at, category, title, message, event_key) "
            "VALUES (?, ?, ?, ?, ?)",
            (timestamp, str(category), str(title), str(message), event_key),
        )
        self.connection.commit()
        return int(result.lastrowid) if result.rowcount else 0

    def remove_repeated_notifications(self) -> int:
        """Remove historic popup floods while keeping the first daily event."""
        before = int(self.cursor.execute(
            "SELECT COUNT(*) AS count FROM notifications"
        ).fetchone()["count"])
        self.cursor.execute(
            """
            DELETE FROM notifications
            WHERE id IN (
                SELECT duplicate.id
                FROM notifications AS duplicate
                JOIN notifications AS first
                  ON substr(duplicate.created_at, 1, 10) = substr(first.created_at, 1, 10)
                 AND duplicate.category = first.category
                 AND duplicate.title = first.title
                 AND duplicate.id > first.id
                WHERE duplicate.category IN ('support_resistance', 'auto_opportunity')
                   OR duplicate.message = first.message
            )
            """
        )
        self.connection.commit()
        after = int(self.cursor.execute(
            "SELECT COUNT(*) AS count FROM notifications"
        ).fetchone()["count"])
        return before - after

    def get_notifications(
        self, *, today_only: bool = False, unread_only: bool = False, limit: int = 1000
    ) -> list[sqlite3.Row]:
        clauses, values = [], []
        if today_only:
            clauses.append("substr(created_at, 1, 10) = ?")
            values.append(datetime.now().astimezone().strftime("%Y-%m-%d"))
        if unread_only:
            clauses.append("is_read = 0")
        query = "SELECT * FROM notifications"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 10_000)))
        return self.cursor.execute(query, values).fetchall()

    def get_unread_notification_count(self) -> int:
        row = self.cursor.execute(
            "SELECT COUNT(*) AS unread FROM notifications WHERE is_read = 0"
        ).fetchone()
        return int(row["unread"])

    def mark_notification_read(self, notification_id: int, is_read: bool = True) -> bool:
        result = self.cursor.execute(
            "UPDATE notifications SET is_read = ? WHERE id = ?",
            (int(bool(is_read)), int(notification_id)),
        )
        self.connection.commit()
        return bool(result.rowcount)

    def mark_all_notifications_read(self) -> int:
        result = self.cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
        self.connection.commit()
        return int(result.rowcount)

    def export_notifications(
        self, destination: str | Path, *, today_only: bool = False, unread_only: bool = False
    ) -> int:
        rows = self.get_notifications(today_only=today_only, unread_only=unread_only, limit=10_000)
        headers = ("created_at", "status", "category", "title", "message")
        with Path(destination).open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            for row in rows:
                writer.writerow((
                    row["created_at"], "READ" if row["is_read"] else "UNREAD",
                    row["category"], row["title"], row["message"],
                ))
        return len(rows)

    def save_auto_opportunities(self, opportunities: list[dict]) -> int:
        saved = 0
        for item in opportunities:
            candle_time = str(item.get("candle_time") or item.get("scanned_at") or "")
            details = {"evidence": item.get("evidence") or [], "blockers": item.get("blockers") or []}
            details.update({key: value for key, value in (item.get("execution") or {}).items() if value not in (None, "")})
            result = self.cursor.execute(
                """
                INSERT INTO auto_opportunities (
                    scanned_at, candle_time, market_type, symbol, instrument, action, state, score,
                    entry, stop, target_1, target_2, quantity, rr_ratio, exit_rule, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candle_time, market_type, symbol) DO UPDATE SET
                    scanned_at=excluded.scanned_at, instrument=excluded.instrument,
                    action=excluded.action, state=excluded.state, score=excluded.score,
                    entry=excluded.entry, stop=excluded.stop, target_1=excluded.target_1,
                    target_2=excluded.target_2, quantity=excluded.quantity,
                    rr_ratio=excluded.rr_ratio, exit_rule=excluded.exit_rule,
                    details_json=excluded.details_json
                """,
                (
                    item["scanned_at"], candle_time, item["market_type"], item["symbol"], item.get("instrument"),
                    item["action"], item["state"], float(item.get("score") or 0), item.get("entry"), item.get("stop"),
                    item.get("target_1"), item.get("target_2"), item.get("quantity"), item.get("rr_ratio"),
                    item.get("exit_rule", ""), json.dumps(details, ensure_ascii=False, default=str),
                ),
            )
            saved += int(result.rowcount > 0)
        self.connection.commit()
        return saved

    def get_auto_opportunities(self, limit: int = 300):
        return self.cursor.execute(
            "SELECT * FROM auto_opportunities ORDER BY scanned_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit), 3000)),),
        ).fetchall()

    def save_gap_probability_forecast(self, forecast: dict) -> int:
        values = (
            forecast["forecast_date"], forecast["target_date"], forecast["generated_at"],
            str(forecast["symbol"]).upper(), forecast["stage"], forecast["predicted_class"],
            float(forecast["gap_up_probability"]), float(forecast["flat_probability"]),
            float(forecast["gap_down_probability"]), int(forecast["confidence"]),
            int(forecast["data_quality"]), float(forecast["prior_close"]),
            json.dumps(forecast.get("inputs") or {}, ensure_ascii=False, default=str),
            json.dumps(forecast.get("evidence") or [], ensure_ascii=False, default=str),
        )
        self.cursor.execute(
            """
            INSERT INTO gap_probability_forecasts (
                forecast_date, target_date, generated_at, symbol, stage, predicted_class,
                gap_up_probability, flat_probability, gap_down_probability, confidence,
                data_quality, prior_close, inputs_json, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(forecast_date, symbol, stage) DO UPDATE SET
                target_date=excluded.target_date, generated_at=excluded.generated_at,
                predicted_class=excluded.predicted_class,
                gap_up_probability=excluded.gap_up_probability,
                flat_probability=excluded.flat_probability,
                gap_down_probability=excluded.gap_down_probability,
                confidence=excluded.confidence, data_quality=excluded.data_quality,
                prior_close=excluded.prior_close, inputs_json=excluded.inputs_json,
                evidence_json=excluded.evidence_json
            """,
            values,
        )
        self.connection.commit()
        row = self.cursor.execute(
            "SELECT id FROM gap_probability_forecasts WHERE forecast_date=? AND symbol=? AND stage=?",
            (values[0], values[3], values[4]),
        ).fetchone()
        return int(row["id"])

    def get_gap_probability_forecasts(self, symbol: str | None = None, limit: int = 100):
        query, values = "SELECT * FROM gap_probability_forecasts", []
        if symbol:
            query += " WHERE symbol = ?"
            values.append(str(symbol).upper())
        query += " ORDER BY forecast_date DESC, generated_at DESC LIMIT ?"
        values.append(max(1, min(int(limit), 1000)))
        return self.cursor.execute(query, values).fetchall()

    def resolve_gap_probability_outcomes(self, threshold_percent: float = 0.15) -> int:
        """Attach the first saved target-session open to unresolved forecasts."""
        from core.market_session import parse_session_times
        _, session_open, _ = parse_session_times()
        opening_start = session_open.strftime("%H:%M")
        opening_end = (datetime.combine(datetime.today(), session_open) + timedelta(minutes=10)).time().strftime("%H:%M")
        unresolved = self.cursor.execute(
            "SELECT * FROM gap_probability_forecasts WHERE actual_class IS NULL"
        ).fetchall()
        updated = 0
        for row in unresolved:
            try:
                forecast_day = datetime.strptime(row["forecast_date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            candidates = self.cursor.execute(
                """SELECT trade_date, captured_at, open FROM market_snapshots
                   WHERE symbol=? AND timeframe='5m'
                   AND substr(captured_at, 12, 5) BETWEEN ? AND ?
                   ORDER BY captured_at ASC, id ASC""",
                (row["symbol"], opening_start, opening_end),
            ).fetchall()
            opening = None
            for candidate in candidates:
                try:
                    session_day = datetime.strptime(candidate["trade_date"], "%d-%m-%Y").date()
                except ValueError:
                    continue
                if forecast_day < session_day <= forecast_day + timedelta(days=7):
                    opening = candidate
                    break
            if not opening or float(row["prior_close"] or 0) <= 0:
                continue
            actual_open = float(opening["open"])
            gap_percent = (actual_open - float(row["prior_close"])) / float(row["prior_close"]) * 100
            actual_class = "GAP UP" if gap_percent >= threshold_percent else "GAP DOWN" if gap_percent <= -threshold_percent else "FLAT / INSIDE"
            correct = int(actual_class == row["predicted_class"])
            self.cursor.execute(
                """UPDATE gap_probability_forecasts
                   SET target_date=?, actual_open=?, actual_gap_percent=?, actual_class=?, correct=? WHERE id=?""",
                (session_day.isoformat(), actual_open, gap_percent, actual_class, correct, row["id"]),
            )
            updated += 1
        self.connection.commit()
        return updated

    def save_pcr_observation(self, observation: dict) -> int:
        result = self.cursor.execute(
            """INSERT INTO pcr_observations (
                   captured_at, symbol, expiry, call_oi, put_oi, pcr_oi,
                   call_volume, put_volume, pcr_volume, call_oi_change,
                   put_oi_change, sentiment, confidence
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                observation["captured_at"], str(observation["symbol"]).upper(), str(observation["expiry"]),
                float(observation.get("call_oi", 0)), float(observation.get("put_oi", 0)), observation.get("pcr_oi"),
                float(observation.get("call_volume", 0)), float(observation.get("put_volume", 0)), observation.get("pcr_volume"),
                observation.get("call_oi_change"), observation.get("put_oi_change"),
                str(observation.get("sentiment", "UNAVAILABLE")), int(observation.get("confidence", 0)),
            ),
        )
        self.connection.commit()
        return int(result.lastrowid)

    def get_latest_pcr_observation(self, symbol: str, expiry: str | None = None):
        query = "SELECT * FROM pcr_observations WHERE symbol = ?"
        values = [str(symbol).upper()]
        if expiry is not None:
            query += " AND expiry = ?"
            values.append(str(expiry))
        return self.cursor.execute(query + " ORDER BY captured_at DESC, id DESC LIMIT 1", values).fetchone()

    def get_pcr_observations(self, symbol: str, limit: int = 50):
        return self.cursor.execute(
            "SELECT * FROM pcr_observations WHERE symbol = ? ORDER BY captured_at DESC, id DESC LIMIT ?",
            (str(symbol).upper(), max(1, min(int(limit), 500))),
        ).fetchall()

    @staticmethod
    def _calculate_trade_values(trade: Trade) -> tuple[float, float]:
        pnl = round((float(trade.exit) - float(trade.entry)) * int(trade.quantity), 2)
        risk = abs(float(trade.entry) - float(trade.stoploss))
        reward = abs(float(trade.target) - float(trade.entry))
        return pnl, round(reward / risk, 2) if risk else 0.0

    def save_trade(self, trade: Trade) -> int:
        """Persist a validated :class:`Trade` and return its database id."""
        if not trade.symbol.strip():
            raise ValueError("Symbol is required.")
        if trade.entry <= 0 or trade.exit < 0 or trade.stoploss < 0 or trade.target < 0:
            raise ValueError("Prices must be non-negative, and entry must be greater than zero.")
        if trade.quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        pnl, rr_ratio = self._calculate_trade_values(trade)
        analysis = TPSEngine().calculate(trade)
        trade.pnl, trade.rr_ratio = pnl, rr_ratio
        trade.ai_score = analysis["score"]
        trade.ai_decision = analysis["decision"]
        trade.ai_review = ", ".join(analysis["reasons"]) or "No technical confirmations recorded."

        values = (
            trade.trade_date, trade.trade_time, trade.market, trade.symbol.upper(),
            trade.expiry, trade.strike, trade.option, trade.entry, trade.exit,
            trade.stoploss, trade.target, trade.quantity, pnl, rr_ratio, trade.setup,
            int(trade.trend), int(trade.vwap), int(trade.ema), int(trade.volume), int(trade.oi),
            trade.psychology_before, trade.psychology_after, trade.mistake, trade.confidence,
            trade.ai_score, trade.ai_decision, trade.ai_review, trade.notes, trade.screenshot,
            "CLOSED", "MANUAL EXIT", datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds"),
        )
        self.cursor.execute(
            """
            INSERT INTO trades (
                trade_date, trade_time, market, symbol, expiry, strike, option_type,
                entry, exit, stoploss, target, quantity, pnl, rr_ratio, setup,
                trend, vwap, ema, volume, oi, psychology_before, psychology_after,
                mistake, confidence, ai_score, ai_decision, ai_review, notes,
                screenshot, status, outcome, closed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.connection.commit()
        return int(self.cursor.lastrowid)

    def save_open_trade(self, trade: Trade) -> int:
        """Persist a planned/manual entry that has no exit yet."""
        if not trade.symbol.strip():
            raise ValueError("Symbol is required.")
        if trade.entry <= 0 or trade.stoploss < 0 or trade.target < 0:
            raise ValueError("Entry must be greater than zero and stop loss/target must be non-negative.")
        if trade.quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        analysis = TPSEngine().calculate(trade)
        ai_score = int(trade.ai_score) if int(trade.ai_score or 0) > 0 else int(analysis["score"])
        ai_decision = str(trade.ai_decision or analysis["decision"])
        ai_review = str(trade.ai_review or ", ".join(analysis["reasons"]) or "No technical confirmations recorded.")
        values = (
            trade.trade_date, trade.trade_time, trade.market, trade.symbol.upper(),
            trade.expiry, trade.strike, trade.option, trade.entry, 0.0,
            trade.stoploss, trade.target, trade.quantity, 0.0, 0.0, trade.setup,
            int(trade.trend), int(trade.vwap), int(trade.ema), int(trade.volume), int(trade.oi),
            trade.psychology_before, trade.psychology_after, trade.mistake, trade.confidence,
            ai_score, ai_decision, ai_review,
            trade.notes, trade.screenshot, "OPEN", "PENDING", None, datetime.now().isoformat(timespec="seconds"),
        )
        self.cursor.execute(
            """
            INSERT INTO trades (
                trade_date, trade_time, market, symbol, expiry, strike, option_type,
                entry, exit, stoploss, target, quantity, pnl, rr_ratio, setup,
                trend, vwap, ema, volume, oi, psychology_before, psychology_after,
                mistake, confidence, ai_score, ai_decision, ai_review, notes,
                screenshot, status, outcome, closed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.connection.commit()
        return int(self.cursor.lastrowid)

    def save_paper_trade(self, plan: dict) -> int:
        timing = plan.get("signal_timing") or {}
        entry_delay = timing.get("entry_delay_seconds")
        if entry_delay is None and timing.get("first_valid_at") and timing.get("final_capture_at"):
            try:
                entry_delay = max(0, int((
                    datetime.fromisoformat(timing["final_capture_at"])
                    - datetime.fromisoformat(timing["first_valid_at"])
                ).total_seconds()))
            except (TypeError, ValueError):
                entry_delay = None
        """Store a simulated one-lot/selected-lot plan; never send a broker order."""
        contract = plan["contract"]
        trade = Trade(
            trade_date=datetime.now().strftime("%d-%m-%Y"), trade_time=datetime.now().strftime("%H:%M"),
            market="PAPER OPTIONS", symbol=plan["underlying"], expiry=str(contract.get("expiry", "")),
            strike=f"{float(contract['strike']):.0f}", option=plan["option_type"], entry=float(plan["entry"]),
            exit=0.0, stoploss=float(plan["stoploss"]), target=float(plan["target"]), quantity=int(plan["quantity"]),
            setup=plan.get("rule_version", "TPS paper trade"), confidence=int(plan.get("confidence", 0)),
            trend=True, vwap=True, ema=True, volume=True, oi=True, psychology_before="Paper simulation",
            ai_score=int(plan.get("confidence", 0)), ai_decision="PAPER TRADE CAPTURED",
            ai_review=json.dumps(plan.get("decision_audit", {}), ensure_ascii=False, default=str),
            notes=json.dumps({"paper_trade": True, "plan": plan}, ensure_ascii=False, default=str),
        )
        trade_id = self.save_open_trade(trade)
        self.cursor.execute(
            """INSERT INTO paper_trade_links
               (trade_id, exchange, token, contract_symbol, initial_stoploss, trailing_stoploss,
                entry_lateness_seconds, premium_spread_percent, initial_atr, plan_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, str(contract["exchange"]), str(contract["token"]), str(contract["symbol"]),
             float(plan["stoploss"]), float(plan["stoploss"]),
             entry_delay,
             (plan.get("execution_safety") or {}).get("spread_percent"),
             (plan.get("evidence_context") or {}).get("atr_14"),
             json.dumps(plan, ensure_ascii=False, default=str)),
        )
        self.cursor.execute(
            "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
            (trade_id, datetime.now().isoformat(timespec="seconds"), "PAPER_ENTRY", "Paper trade captured",
             f"{contract['symbol']} entry {float(plan['entry']):.2f}; stop {float(plan['stoploss']):.2f}; target {float(plan['target']):.2f}."),
        )
        self.connection.commit()
        return trade_id

    def has_recent_paper_thesis(self, fingerprint: str, minutes: int = 15) -> bool:
        """Do not count the same market thesis as independent validation evidence."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(minutes=max(1, int(minutes)))).isoformat(timespec="seconds")
        rows = self.cursor.execute(
            """SELECT p.plan_json FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id
               WHERE t.created_at >= ? ORDER BY t.id DESC LIMIT 50""", (cutoff,),
        ).fetchall()
        for row in rows:
            try:
                saved = json.loads(row["plan_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if str(saved.get("validation_fingerprint") or "") == str(fingerprint):
                return True
        return False

    def monitor_paper_trades(self, client, settings=None, now=None) -> list[dict]:
        """Close simulated trades on a verified option quote only; no order API is used."""
        from core.market_session import IST, parse_session_times
        from datetime import timedelta

        settings = settings or {}
        now = now or datetime.now(IST)
        now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        rows = self.cursor.execute(
            """SELECT t.*, p.exchange, p.token, p.contract_symbol, p.last_ltp, p.min_ltp, p.max_ltp,
                      p.last_alert_level, p.initial_stoploss, p.trailing_stoploss, p.plan_json FROM trades t
               JOIN paper_trade_links p ON p.trade_id = t.id WHERE t.status = 'OPEN'"""
        ).fetchall()
        closed = []

        def close_on_last_verified_at_time_exit(row, reason: str) -> bool:
            """Use a previously verified premium only for the mandatory paper time exit."""
            close_at = datetime.combine(now.date(), parse_session_times(settings)[2], IST)
            exit_window = settings.get("time_exit_minutes_before_close")
            time_exit = exit_window is not None and now >= close_at - timedelta(minutes=int(exit_window))
            last_ltp = float(row["last_ltp"] or 0)
            if not time_exit or last_ltp <= 0 or not self.close_trade(int(row["id"]), last_ltp, "TIME EXIT"):
                return False
            created_at = datetime.now().isoformat(timespec="seconds")
            self.cursor.execute(
                "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                (int(row["id"]), created_at, "TIME_EXIT_LAST_VERIFIED",
                 "Paper time exit used last verified premium",
                 f"Fresh exit quote was unavailable ({reason}); paper trade closed at last verified LTP {last_ltp:.2f}."),
            )
            self.cursor.execute(
                "UPDATE trade_alerts SET status = 'RESOLVED' WHERE trade_id = ? AND alert_type = 'TIME_EXIT_LAST_VERIFIED'",
                (int(row["id"]),),
            )
            closed.append({"trade_id": int(row["id"]), "symbol": row["contract_symbol"], "ltp": last_ltp, "outcome": "TIME EXIT"})
            return True

        for row in rows:
            try:
                from services.market_data_hub import MarketDataHub
                quote = MarketDataHub.quote(client, row["exchange"], row["token"], ttl_seconds=1.0, force=True)
                # A long option can normally be exited near the executable bid,
                # not at an optimistic last-traded price.
                ltp = float(quote.get("bid", quote.get("bestBidPrice", 0)) or quote.get("ltp", 0) or 0)
            except (RuntimeError, ValueError, TypeError, KeyError) as error:
                # One unavailable contract must never pause monitoring for all
                # other open paper positions. Time exit can use the last
                # already-verified premium, clearly recorded as a fallback.
                close_on_last_verified_at_time_exit(row, str(error))
                continue
            if ltp <= 0:
                close_on_last_verified_at_time_exit(row, "broker returned a zero/blank premium")
                continue
            minimum = min(ltp, float(row["min_ltp"])) if row["min_ltp"] is not None else ltp
            maximum = max(ltp, float(row["max_ltp"])) if row["max_ltp"] is not None else ltp
            initial_stop = float(row["initial_stoploss"] if row["initial_stoploss"] is not None else row["stoploss"])
            active_stop = float(row["trailing_stoploss"] if row["trailing_stoploss"] is not None else row["stoploss"])
            risk = max(float(row["entry"]) - initial_stop, 0.000001)
            entry = float(row["entry"])
            target = float(row["target"])
            if settings.get("trailing_stop_enabled", True):
                # Capital-protection ladder based only on already-observed
                # option premiums (no target fabrication or look-ahead).
                if maximum >= entry + .50 * risk:
                    active_stop = max(active_stop, entry)
                if maximum >= entry + float(settings.get("trailing_stop_trigger_r", 1)) * risk:
                    active_stop = max(active_stop, entry + float(settings.get("trailing_stop_lock_r", .25)) * risk)
                target_distance = max(target - entry, 0.0)
                if target_distance and maximum >= entry + .90 * target_distance:
                    active_stop = max(active_stop, entry + .65 * target_distance)
            if active_stop > float(row["trailing_stoploss"] or initial_stop):
                self.cursor.execute(
                    "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                    (int(row["id"]), datetime.now().isoformat(timespec="seconds"), f"TRAIL_{active_stop:.2f}",
                     "Premium trailing stop raised", f"{row['contract_symbol']} trailing stop moved to {active_stop:.2f}."),
                )
            loss_progress = (float(row["entry"]) - ltp) / risk
            alert_level = "CRITICAL" if loss_progress >= .90 else "STRONG" if loss_progress >= .75 else "EARLY" if loss_progress >= .50 else None
            self.cursor.execute(
                """UPDATE paper_trade_links SET last_ltp = ?, min_ltp = ?, max_ltp = ?,
                          last_alert_level = COALESCE(?, last_alert_level), trailing_stoploss = ?,
                          mae = ?, mfe = ? WHERE trade_id = ?""",
                (ltp, minimum, maximum, alert_level, active_stop,
                 round(max(0.0, float(row["entry"]) - minimum), 2),
                 round(max(0.0, maximum - float(row["entry"])), 2), int(row["id"])),
            )
            if alert_level:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                    (int(row["id"]), datetime.now().isoformat(timespec="seconds"), f"PREMIUM_SL_{alert_level}",
                     f"{alert_level.title()} option-premium stop warning",
                     f"{row['contract_symbol']} LTP {ltp:.2f}; active stop {active_stop:.2f}; "
                     f"{max(0, loss_progress) * 100:.0f}% of entry-to-stop risk used."),
                )
            close_at = datetime.combine(now.date(), parse_session_times(settings)[2], IST)
            exit_window = settings.get("time_exit_minutes_before_close")
            time_exit = exit_window is not None and now >= close_at - timedelta(minutes=int(exit_window))
            stop_outcome = "TRAILING STOP HIT" if active_stop > initial_stop else "STOP LOSS HIT"
            outcome = "TARGET HIT" if ltp >= float(row["target"]) else stop_outcome if ltp <= active_stop else "TIME EXIT" if time_exit else None
            if outcome and self.close_trade(int(row["id"]), ltp, outcome):
                closed.append({"trade_id": int(row["id"]), "symbol": row["contract_symbol"], "ltp": ltp, "outcome": outcome})
            elif not outcome:
                self.evaluate_open_trade_alerts(row["symbol"])
        self.connection.commit()
        return closed

    def get_paper_trade_monitoring(self) -> list[dict]:
        """Return live premium, MAE/MFE and active stop-proximity alerts."""
        rows = self.cursor.execute(
            """SELECT t.id, t.entry, t.stoploss, t.target, p.contract_symbol, p.last_ltp,
                      p.min_ltp, p.max_ltp, p.last_alert_level, p.trailing_stoploss
               FROM trades t JOIN paper_trade_links p ON p.trade_id = t.id
               WHERE t.status = 'OPEN' ORDER BY t.id DESC"""
        ).fetchall()
        return [{
            "trade_id": int(row["id"]), "symbol": row["contract_symbol"], "ltp": row["last_ltp"],
            "mae": round(float(row["entry"]) - float(row["min_ltp"]), 2) if row["min_ltp"] is not None else 0,
            "mfe": round(float(row["max_ltp"]) - float(row["entry"]), 2) if row["max_ltp"] is not None else 0,
            "alert": row["last_alert_level"], "stoploss": float(row["trailing_stoploss"] or row["stoploss"]),
            "initial_stoploss": float(row["stoploss"]), "target": float(row["target"]),
        } for row in rows]

    def paper_trade_progress(self, trade_date: str | None = None) -> dict:
        """Return forward-test progress without mixing it with manual real trades."""
        where, values = "", ()
        if trade_date:
            where, values = "WHERE t.trade_date = ?", (trade_date,)
        row = self.cursor.execute(
            f"""SELECT COUNT(*) AS trades, COUNT(DISTINCT t.trade_date) AS days,
                       SUM(CASE WHEN t.status = 'OPEN' THEN 1 ELSE 0 END) AS open_trades,
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.outcome = 'TARGET HIT' THEN 1 ELSE 0 END) AS target_hits,
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.outcome IN ('STOP LOSS HIT','TRAILING STOP HIT') THEN 1 ELSE 0 END) AS stoploss_hits,
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.outcome = 'TIME EXIT' THEN 1 ELSE 0 END) AS time_exits,
                       SUM(CASE WHEN t.status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_trades,
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.pnl > 0 THEN 1 ELSE 0 END) AS profitable_closes
                FROM trades t JOIN paper_trade_links p ON p.trade_id = t.id {where}""", values,
        ).fetchone()
        result = {key: int(row[key] or 0) for key in (
            "trades", "days", "open_trades", "target_hits", "stoploss_hits", "time_exits", "closed_trades", "profitable_closes"
        )}
        decisive = result["target_hits"] + result["stoploss_hits"]
        result["target_vs_stop_accuracy"] = round(result["target_hits"] * 100 / decisive, 1) if decisive else 0.0
        result["closed_trade_win_rate"] = round(result["profitable_closes"] * 100 / result["closed_trades"], 1) if result["closed_trades"] else 0.0
        pnl_row = self.cursor.execute(
            f"SELECT COALESCE(SUM(pnl), 0) AS realized_pnl FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id {where} AND t.status='CLOSED'" if where
            else "SELECT COALESCE(SUM(t.pnl), 0) AS realized_pnl FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id WHERE t.status='CLOSED'",
            values,
        ).fetchone()
        result["realized_pnl"] = float(pnl_row["realized_pnl"] or 0)
        return result

    def paper_trade_cooldown_remaining(self, minutes: int, now=None) -> int:
        """Return whole minutes remaining since the latest paper execution."""
        from datetime import timedelta

        if int(minutes) <= 0:
            return 0
        row = self.cursor.execute(
            """SELECT t.created_at FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id
               ORDER BY t.created_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return 0
        now = now or datetime.now()
        created = datetime.fromisoformat(row["created_at"])
        remaining = created + timedelta(minutes=int(minutes)) - now.replace(tzinfo=None)
        return max(0, int((remaining.total_seconds() + 59) // 60))

    def paper_loss_streak(self) -> dict:
        """Return the latest consecutive closed-paper loss streak."""
        rows = self.cursor.execute(
            """SELECT t.pnl, t.outcome, t.closed_at, t.created_at
               FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id
               WHERE t.status='CLOSED' ORDER BY COALESCE(t.closed_at, t.created_at) DESC, t.id DESC"""
        ).fetchall()
        count = 0
        latest_closed_at = None
        loss_outcomes = {"STOP LOSS HIT", "TRAILING STOP HIT"}
        for row in rows:
            is_loss = float(row["pnl"] or 0) < 0 or str(row["outcome"] or "").upper() in loss_outcomes
            if not is_loss:
                break
            if latest_closed_at is None:
                latest_closed_at = row["closed_at"] or row["created_at"]
            count += 1
        return {"count": count, "latest_closed_at": latest_closed_at}

    def close_trade(self, trade_id: int, exit_price: float, outcome: str = "MANUAL EXIT") -> bool:
        """Record the actual exit for one previously saved open trade."""
        if exit_price <= 0:
            raise ValueError("Enter an actual exit price greater than zero.")
        outcome = str(outcome).upper()
        if outcome not in {"TARGET HIT", "STOP LOSS HIT", "MANUAL EXIT", "TIME EXIT", "TRAILING STOP HIT"}:
            raise ValueError("Choose Target Hit, Stop Loss Hit, Time Exit, Trailing Stop Hit, or Manual Exit.")
        row = self.cursor.execute("SELECT entry, stoploss, target, quantity, status FROM trades WHERE id = ?", (int(trade_id),)).fetchone()
        if not row:
            return False
        if row["status"] != "OPEN":
            raise ValueError("This trade is already closed.")
        gross_pnl = (float(exit_price) - float(row["entry"])) * int(row["quantity"])
        friction = 0.0
        link = self.cursor.execute("SELECT plan_json FROM paper_trade_links WHERE trade_id=?", (int(trade_id),)).fetchone()
        if link:
            try:
                plan = json.loads(link["plan_json"] or "{}")
                friction = float(plan.get("estimated_round_trip_cost") or 0)
            except (TypeError, ValueError):
                friction = 0.0
        pnl = round(gross_pnl - friction, 2)
        risk = abs(float(row["entry"]) - float(row["stoploss"]))
        reward = abs(float(row["target"]) - float(row["entry"]))
        rr_ratio = round(reward / risk, 2) if risk else 0.0
        result = self.cursor.execute(
            "UPDATE trades SET exit = ?, pnl = ?, rr_ratio = ?, status = 'CLOSED', outcome = ?, closed_at = ? WHERE id = ? AND status = 'OPEN'",
            (float(exit_price), pnl, rr_ratio, outcome, datetime.now().isoformat(timespec="seconds"), int(trade_id)),
        )
        closed = result.rowcount == 1
        if closed:
            self.cursor.execute(
                "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                (int(trade_id), datetime.now().isoformat(timespec="seconds"), f"PAPER_EXIT_{outcome}",
                 f"Paper trade closed: {outcome}",
                 f"Exit {float(exit_price):.2f}; gross P&L {gross_pnl:.2f}; friction {friction:.2f}; net P&L {pnl:.2f}; R:R {rr_ratio:.2f}."),
            )
        self.connection.commit()
        if closed:
            self.cursor.execute("UPDATE trade_alerts SET status = 'RESOLVED' WHERE trade_id = ? AND status = 'ACTIVE'", (int(trade_id),))
            self._save_automatic_outcome_review(int(trade_id))
            self.connection.commit()
        return closed

    def _save_automatic_outcome_review(self, trade_id: int) -> None:
        """Create an immutable, explainable postmortem as part of every automatic close."""
        from engine.trade_outcome_memory import build_outcome_review

        row = self.cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        link = self.cursor.execute("SELECT plan_json, mfe, mae FROM paper_trade_links WHERE trade_id = ?", (trade_id,)).fetchone()
        if not row:
            return
        review = build_outcome_review(dict(row), link["plan_json"] if link else None, dict(link) if link else {})
        self.cursor.execute(
            """INSERT INTO trade_outcome_reviews
               (trade_id, generated_at, outcome, fingerprint_json, review_text, solution_text, mfe, mae, pnl)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_id) DO UPDATE SET generated_at=excluded.generated_at,
               outcome=excluded.outcome, fingerprint_json=excluded.fingerprint_json,
               review_text=excluded.review_text, solution_text=excluded.solution_text,
               mfe=excluded.mfe, mae=excluded.mae, pnl=excluded.pnl""",
            (trade_id, datetime.now().isoformat(timespec="seconds"), row["outcome"],
             json.dumps(review["fingerprint"], ensure_ascii=False), review["finding"], review["solution"],
             review["mfe"], review["mae"], review["pnl"]),
        )

    def get_trade_outcome_review(self, trade_id: int) -> sqlite3.Row | None:
        return self.cursor.execute("SELECT * FROM trade_outcome_reviews WHERE trade_id = ?", (int(trade_id),)).fetchone()

    def find_trade_outcome_analogs(self, fingerprint: dict, minimum_similarity: float = 78, limit: int = 3) -> list[dict]:
        from engine.trade_outcome_memory import similarity_score

        matches = []
        for row in self.cursor.execute(
            """SELECT r.*, t.trade_date, t.symbol, t.option_type, t.strike
               FROM trade_outcome_reviews r JOIN trades t ON t.id = r.trade_id
               ORDER BY r.generated_at DESC LIMIT 250"""
        ).fetchall():
            historical = json.loads(row["fingerprint_json"] or "{}")
            similarity = similarity_score(fingerprint, historical)
            if similarity >= float(minimum_similarity):
                item = dict(row)
                item["similarity"] = similarity
                matches.append(item)
        return sorted(matches, key=lambda item: item["similarity"], reverse=True)[:int(limit)]

    def get_trade(self, trade_id: int) -> sqlite3.Row | None:
        return self.cursor.execute("SELECT * FROM trades WHERE id = ?", (int(trade_id),)).fetchone()

    def get_all_trades(self) -> list[sqlite3.Row]:
        return self.cursor.execute(
            """
            SELECT trade_date, trade_time, symbol, option_type, entry, exit,
                   quantity, pnl, rr_ratio, psychology_before, ai_score, ai_decision
            FROM trades ORDER BY id DESC
            """
        ).fetchall()

    def get_journal_rows(self) -> list[sqlite3.Row]:
        """Return rows with IDs for display and safe deletion in the journal."""
        return self.cursor.execute(
            """
            SELECT id, trade_date, trade_time, symbol, strike, option_type, entry, stoploss, target, exit, status, outcome,
                   quantity, pnl, rr_ratio, psychology_before, ai_score, ai_decision
            FROM trades ORDER BY id DESC
            """
        ).fetchall()

    def delete_trade(self, trade_id: int) -> bool:
        """Delete one selected trade. Returns False when it no longer exists."""
        result = self.cursor.execute("DELETE FROM trades WHERE id = ?", (int(trade_id),))
        self.connection.commit()
        return result.rowcount == 1

    def export_csv(self, destination: str | Path) -> int:
        """Export journal records as a portable CSV file and return row count."""
        rows = self.cursor.execute(
            """
            SELECT trade_date, trade_time, market, symbol, expiry, strike, option_type,
                   entry, exit, stoploss, target, quantity, pnl, rr_ratio, setup, status, outcome, closed_at,
                   psychology_before, psychology_after, mistake, confidence, ai_score,
                   ai_decision, ai_review, notes, created_at
            FROM trades ORDER BY id DESC
            """
        ).fetchall()
        headers = [column[0] for column in self.cursor.description]
        with Path(destination).open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(rows)
        return len(rows)

    def get_summary(self) -> dict[str, float | int]:
        """Return portfolio-level metrics for the local dashboard and reports."""
        row = self.cursor.execute(
            """
            SELECT COUNT(*) AS trades,
                   COALESCE(SUM(pnl), 0) AS pnl,
                   COALESCE(AVG(ai_score), 0) AS average_ai,
                   COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS winning_trades
            FROM trades
            """
        ).fetchone()
        trades = int(row["trades"])
        wins = int(row["winning_trades"])
        return {
            "trades": trades,
            "pnl": round(float(row["pnl"]), 2),
            "average_ai": round(float(row["average_ai"]), 1),
            "winning_trades": wins,
            "win_rate": round((wins / trades) * 100, 1) if trades else 0.0,
        }

    def get_ai_outcome_report(self) -> dict[str, float | int]:
        """Summarise closed AI-reviewed trades without treating it as proof of future performance."""
        row = self.cursor.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_trades,
                SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_trades,
                SUM(CASE WHEN status = 'CLOSED' AND outcome = 'TARGET HIT' THEN 1 ELSE 0 END) AS target_hits,
                SUM(CASE WHEN status = 'CLOSED' AND outcome = 'STOP LOSS HIT' THEN 1 ELSE 0 END) AS stoploss_hits,
                SUM(CASE WHEN status = 'CLOSED' AND outcome = 'MANUAL EXIT' THEN 1 ELSE 0 END) AS manual_exits
            FROM trades
            """
        ).fetchone()
        target_hits = int(row["target_hits"] or 0)
        stoploss_hits = int(row["stoploss_hits"] or 0)
        decisive = target_hits + stoploss_hits
        return {
            "open_trades": int(row["open_trades"] or 0),
            "closed_trades": int(row["closed_trades"] or 0),
            "target_hits": target_hits,
            "stoploss_hits": stoploss_hits,
            "manual_exits": int(row["manual_exits"] or 0),
            "target_vs_stop_accuracy": round((target_hits / decisive) * 100, 1) if decisive else 0.0,
        }

    def get_validation_report(self) -> dict[str, float | int | str]:
        """Summarise fully-confirmed closed journal trades as evidence, not a forecast."""
        row = self.cursor.execute(
            """
            SELECT COUNT(*) AS samples,
                   SUM(CASE WHEN outcome = 'TARGET HIT' THEN 1 ELSE 0 END) AS target_hits,
                   SUM(CASE WHEN outcome = 'STOP LOSS HIT' THEN 1 ELSE 0 END) AS stoploss_hits
            FROM trades
            WHERE status = 'CLOSED' AND trend = 1 AND vwap = 1 AND ema = 1 AND volume = 1 AND oi = 1
            """
        ).fetchone()
        samples = int(row["samples"] or 0)
        target_hits, stoploss_hits = int(row["target_hits"] or 0), int(row["stoploss_hits"] or 0)
        decisive = target_hits + stoploss_hits
        accuracy = round(target_hits * 100 / decisive, 1) if decisive else 0.0
        if samples < 30:
            status = "Insufficient live sample: record at least 30 fully-confirmed closed trades."
        elif decisive < 20:
            status = "Too few target/stop outcomes to assess this setup reliably."
        elif accuracy >= 60:
            status = "Promising recorded sample; keep fixed risk and continue forward validation."
        else:
            status = "Recorded result does not validate increasing risk; review the rule and market regime."
        return {"samples": samples, "target_hits": target_hits, "stoploss_hits": stoploss_hits, "accuracy": accuracy, "status": status}

    def get_rule_version_report(self) -> list[sqlite3.Row]:
        """Compare recorded closed outcomes by the rule/setup version used."""
        return self.cursor.execute(
            """
            SELECT COALESCE(NULLIF(setup, ''), 'Manual / unclassified') AS rule_version,
                   COUNT(*) AS samples,
                   SUM(CASE WHEN outcome = 'TARGET HIT' THEN 1 ELSE 0 END) AS target_hits,
                   SUM(CASE WHEN outcome = 'STOP LOSS HIT' THEN 1 ELSE 0 END) AS stoploss_hits,
                   ROUND(COALESCE(SUM(pnl), 0), 2) AS net_pnl
            FROM trades WHERE status = 'CLOSED'
            GROUP BY COALESCE(NULLIF(setup, ''), 'Manual / unclassified')
            ORDER BY samples DESC, rule_version ASC
            """
        ).fetchall()

    def save_market_snapshot(self, snapshot: dict) -> bool:
        """Persist a timed, read-only market/option-chain observation."""
        columns = (
            "captured_at", "trade_date", "symbol", "timeframe", "open", "high", "low", "close",
            "volume", "volume_ema", "ema_5", "ema_20", "ema_50", "vwap", "supertrend",
            "rsi_14", "atr_14", "oi_pcr", "volume_pcr", "oi_pcr_change", "volume_pcr_change", "put_support", "call_resistance", "option_contracts",
        )
        values = tuple(snapshot.get(column) for column in columns)
        result = self.cursor.execute(
            f"INSERT OR IGNORE INTO market_snapshots ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        self.connection.commit()
        return result.rowcount == 1

    def save_index_candle_analysis(self, analysis: dict) -> bool:
        columns = (
            "trade_date", "candle_time", "analyzed_at", "symbol", "state", "direction", "aggression",
            "open", "high", "low", "close", "move_points", "range_points", "range_ratio", "volume", "volume_ratio",
            "oi_direction", "oi_quality", "call_oi", "put_oi", "call_coi", "put_coi", "put_wall", "put_wall_health",
            "call_wall", "call_wall_health", "source_completeness", "explanation", "details_json",
            "atm_strike", "atm_ce_premium", "atm_pe_premium", "oi_pcr", "volume_pcr",
        )
        values = tuple(analysis.get(c) for c in columns)
        result = self.cursor.execute(
            f"INSERT OR IGNORE INTO index_candle_analyses ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", values,
        )
        self.connection.commit()
        return result.rowcount == 1

    def get_index_candle_analyses(self, trade_date: str) -> list[sqlite3.Row]:
        return self.cursor.execute(
            "SELECT * FROM index_candle_analyses WHERE trade_date = ? ORDER BY candle_time DESC, symbol ASC", (trade_date,),
        ).fetchall()

    def get_index_candle_history(self, symbol: str, limit: int = 10000) -> list[sqlite3.Row]:
        return self.cursor.execute(
            "SELECT * FROM index_candle_analyses WHERE symbol=? ORDER BY candle_time DESC LIMIT ?",
            (str(symbol).upper(), max(1, min(int(limit), 50000))),
        ).fetchall()

    def save_index_daily_analysis(self, report: dict) -> None:
        self.cursor.execute(
            """INSERT INTO index_daily_analyses
               (trade_date, generated_at, market_state, source_completeness, summary_text, details_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date) DO UPDATE SET generated_at=excluded.generated_at,
               market_state=excluded.market_state, source_completeness=excluded.source_completeness,
               summary_text=excluded.summary_text, details_json=excluded.details_json""",
            tuple(report.get(k) for k in ("trade_date", "generated_at", "market_state", "source_completeness", "summary_text", "details_json")),
        )
        self.connection.commit()

    def get_index_daily_analysis(self, trade_date: str) -> sqlite3.Row | None:
        return self.cursor.execute("SELECT * FROM index_daily_analyses WHERE trade_date = ?", (trade_date,)).fetchone()

    def get_market_snapshots(self, trade_date: str | None = None) -> list[sqlite3.Row]:
        if trade_date:
            return self.cursor.execute(
                "SELECT * FROM market_snapshots WHERE trade_date = ? ORDER BY captured_at ASC, timeframe ASC",
                (trade_date,),
            ).fetchall()
        return self.cursor.execute("SELECT * FROM market_snapshots ORDER BY captured_at DESC, timeframe ASC").fetchall()

    def get_latest_market_snapshot(self, symbol: str, timeframe: str) -> sqlite3.Row | None:
        return self.cursor.execute(
            "SELECT * FROM market_snapshots WHERE symbol = ? AND timeframe = ? ORDER BY captured_at DESC LIMIT 1",
            (str(symbol).upper(), str(timeframe)),
        ).fetchone()

    def save_auto_trade_attempt(self, symbol: str, result: dict) -> bool:
        """Persist one completed-candle auto-paper evaluation for audit and review."""
        attempt = result.get("attempt") or {}
        chart = attempt.get("chart") or {}
        strategy = chart.get("strategy") or {}
        timing = attempt.get("timing") or {}
        capture = attempt.get("capture") or {}
        candidate = str(attempt.get("candidate") or "").upper()
        selected_side = (strategy.get("side_evaluations") or {}).get(candidate) or {}
        zones = strategy.get("zones") or {}
        environment = chart.get("market_environment") or {}
        checked_at = str(attempt.get("checked_at") or datetime.now().isoformat(timespec="seconds"))
        candle_time = attempt.get("candle_time")
        data_gaps = list(attempt.get("data_gaps") or chart.get("data_gaps") or [])
        safety_blockers = list(attempt.get("safety_blockers") or [])
        secondary_warnings = list(attempt.get("secondary_warnings") or chart.get("secondary_warnings") or [])
        primary_blocker = attempt.get("primary_blocker") or chart.get("primary_blocker")
        outcome = str(attempt.get("outcome") or result.get("attempt_outcome") or "").upper()
        if outcome not in {"DATA GAP", "SAFETY BLOCK", "STRATEGY REJECT", "CANDIDATE", "CAPTURED"}:
            strategy_qualified = bool(chart.get("trade_ready") or strategy.get("trade_ready"))
            outcome = (
                "CAPTURED" if result.get("plan") else "DATA GAP" if data_gaps or result.get("retry_pending") or not chart
                else "SAFETY BLOCK" if safety_blockers else "CANDIDATE" if strategy_qualified
                else "STRATEGY REJECT"
            )
        volume = capture.get("volume")
        volume_ratio = capture.get("volume_ratio")
        threshold = float(environment.get("volume_threshold") or 1.5)
        volume_reason = (
            "MISSING_PROVIDER_VOLUME" if volume in (None, "", 0, 0.0)
            else "LOW_VIX_STRICT_BENCHMARK" if environment.get("regime") == "LOW VOLATILITY" and float(volume_ratio or 0) < threshold
            else "WEAK_PARTICIPATION" if float(volume_ratio or 0) < threshold
            else "DIRECTIONAL_VOLUME_CONFIRMED"
        )
        support_match = bool(zones.get("support_confluence"))
        resistance_match = bool(zones.get("resistance_confluence"))
        confluence = "BOTH" if support_match and resistance_match else "SUPPORT" if support_match else "RESISTANCE" if resistance_match else "NONE"
        relevant_levels = (
            (zones.get("chart_resistance"), zones.get("oi_resistance")) if candidate == "CE"
            else (zones.get("chart_support"), zones.get("oi_support"))
        )
        level_distances = [abs(float(capture.get("close")) - float(level)) for level in relevant_levels if level not in (None, "") and capture.get("close") not in (None, "")]
        atr = float(capture.get("atr_14") or 0)
        level_distance_atr = round(min(level_distances) / atr, 3) if level_distances and atr > 0 else None
        level_age_seconds = None
        try:
            level_age_seconds = max(0, int((datetime.fromisoformat(checked_at).replace(tzinfo=None) - datetime.fromisoformat(str(candle_time)).replace(tzinfo=None)).total_seconds()))
        except (TypeError, ValueError):
            pass
        evidence_states = (
            chart.get("evidence_states")
            or strategy.get("evidence_states")
            or attempt.get("evidence_states")
            or {}
        )
        values = (
            checked_at, candle_time, datetime.fromisoformat(checked_at).strftime("%d-%m-%Y"), str(symbol).upper(),
            attempt.get("future_symbol"), outcome, chart.get("decision"), attempt.get("candidate"),
            strategy.get("passed"), strategy.get("total", 6) if strategy else None, chart.get("score"),
            result.get("trade_id"), result.get("status", "Auto paper cycle completed"),
            timing.get("signal_discovery_at"), timing.get("first_valid_trigger_at"),
            timing.get("final_capture_at"), timing.get("delay_seconds"), timing.get("stage"),
            volume_reason, zones.get("chart_support"), zones.get("chart_resistance"),
            zones.get("oi_support"), zones.get("oi_resistance"), confluence,
            level_distance_atr, level_age_seconds, chart.get("provider") or capture.get("provider"),
            capture.get("provider_data_age_seconds"),
            primary_blocker,
            json.dumps(secondary_warnings, ensure_ascii=False, default=str),
            json.dumps(evidence_states, ensure_ascii=False, default=str),
            json.dumps({
                "complete": not bool(data_gaps), "data_gaps": data_gaps,
                "total": len(evidence_states),
                "known": sum(str(value).upper() != "UNKNOWN" for value in evidence_states.values()),
            }, ensure_ascii=False, default=str),
            json.dumps(result, ensure_ascii=False, default=str),
        )
        serialized = values[-1]
        existing = None
        if candle_time:
            existing = self.cursor.execute(
                "SELECT id, details_json FROM auto_trade_attempts WHERE symbol = ? AND candle_time = ?",
                (str(symbol).upper(), candle_time),
            ).fetchone()
        if existing and existing["details_json"] == serialized:
            return False
        if existing:
            self.cursor.execute(
                """UPDATE auto_trade_attempts SET checked_at = ?, trade_date = ?, future_symbol = ?, outcome = ?,
                          decision = ?, candidate = ?, confirmations_passed = ?, confirmations_total = ?, score = ?,
                          trade_id = ?, status_text = ?, signal_discovered_at = ?, first_valid_trigger_at = ?,
                          final_capture_at = ?, timing_delay_seconds = ?, timing_stage = ?, volume_reason_code = ?,
                          chart_support = ?, chart_resistance = ?, oi_support = ?, oi_resistance = ?,
                          level_confluence = ?, level_distance_atr = ?, level_age_seconds = ?, provider = ?,
                          provider_data_age_seconds = ?, primary_blocker = ?, secondary_warnings_json = ?,
                          evidence_states_json = ?, source_completeness_json = ?, details_json = ? WHERE id = ?""",
                (values[0], values[2], values[4], values[5], values[6], values[7], values[8], values[9], values[10],
                 values[11], values[12], *values[13:], existing["id"]),
            )
            self.connection.commit()
            if candle_time:
                try:
                    scheduled_at = (datetime.fromisoformat(str(candle_time)) + timedelta(minutes=5)).isoformat(timespec="seconds")
                except ValueError:
                    scheduled_at = checked_at
                self.save_evaluation_slot(
                    symbol, scheduled_at, str(candle_time),
                    "EVALUATED" if chart else "RETRY", "ATTEMPT_SAVED" if chart else outcome,
                    {"attempt_id": int(existing["id"]), "outcome": outcome}, heartbeat_at=checked_at,
                )
            return True
        result_row = self.cursor.execute(
            """INSERT INTO auto_trade_attempts (
                   checked_at, candle_time, trade_date, symbol, future_symbol, outcome, decision, candidate,
                   confirmations_passed, confirmations_total, score, trade_id, status_text,
                   signal_discovered_at, first_valid_trigger_at, final_capture_at, timing_delay_seconds,
                   timing_stage, volume_reason_code, chart_support, chart_resistance, oi_support, oi_resistance,
                   level_confluence, level_distance_atr, level_age_seconds, provider,
                   provider_data_age_seconds, primary_blocker, secondary_warnings_json,
                   evidence_states_json, source_completeness_json, details_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        inserted = result_row.rowcount == 1
        attempt_id = int(result_row.lastrowid or 0)
        self.connection.commit()
        if candle_time:
            try:
                scheduled_at = (datetime.fromisoformat(str(candle_time)) + timedelta(minutes=5)).isoformat(timespec="seconds")
            except ValueError:
                scheduled_at = checked_at
            self.save_evaluation_slot(
                symbol, scheduled_at, str(candle_time),
                "EVALUATED" if chart else "RETRY", "ATTEMPT_SAVED" if chart else outcome,
                {"attempt_id": attempt_id, "outcome": outcome}, heartbeat_at=checked_at,
            )
        return inserted

    def signal_timing_context(
        self, symbol: str, candidate: str, checked_at: str, candle_time: str | None, stage: str,
    ) -> dict:
        """Build a no-look-ahead timing chain from already saved evaluations."""
        current = datetime.fromisoformat(str(checked_at)).replace(tzinfo=None)
        trade_date = current.strftime("%d-%m-%Y")
        stage = str(stage or "NONE").upper()
        latest = self.cursor.execute(
            """SELECT checked_at, candle_time, signal_discovered_at, first_valid_trigger_at, timing_stage
               FROM auto_trade_attempts
               WHERE trade_date = ? AND symbol = ? AND candidate = ? AND signal_discovered_at IS NOT NULL
               ORDER BY checked_at DESC, id DESC LIMIT 1""",
            (trade_date, str(symbol).upper(), str(candidate).upper()),
        ).fetchone()
        discovery_at = first_valid_at = discovery_candle = None
        if latest and str(latest["timing_stage"] or "") != "CAPTURED":
            previous = datetime.fromisoformat(str(latest["checked_at"])).replace(tzinfo=None)
            if timedelta(0) <= current - previous <= timedelta(minutes=15):
                discovery_at = latest["signal_discovered_at"]
                first_valid_at = latest["first_valid_trigger_at"]
                discovery_candle = latest["candle_time"]
        if stage != "NONE" and not discovery_at:
            discovery_at = current.isoformat(timespec="seconds")
            discovery_candle = candle_time
        if stage in {"FIRST VALID", "CAPTURED"} and not first_valid_at:
            first_valid_at = current.isoformat(timespec="seconds")
        final_capture_at = current.isoformat(timespec="seconds") if stage == "CAPTURED" else None
        endpoint = final_capture_at or first_valid_at
        delay_seconds = None
        if discovery_at and endpoint:
            delay_seconds = max(0, int((datetime.fromisoformat(endpoint) - datetime.fromisoformat(discovery_at)).total_seconds()))
        return {
            "stage": stage,
            "signal_discovery_at": discovery_at,
            "discovery_candle_time": discovery_candle,
            "first_valid_trigger_at": first_valid_at,
            "final_capture_at": final_capture_at,
            "delay_seconds": delay_seconds,
            "no_look_ahead": True,
        }

    def get_auto_trade_attempts(self, trade_date: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
        query, values = "SELECT * FROM auto_trade_attempts", []
        if trade_date:
            query += " WHERE trade_date = ?"
            values.append(trade_date)
        query += " ORDER BY COALESCE(candle_time, checked_at) DESC, id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 5000)))
        return self.cursor.execute(query, values).fetchall()

    def get_trades_for_date(self, trade_date: str) -> list[sqlite3.Row]:
        """Return full journal records for one trading date."""
        return self.cursor.execute(
            "SELECT * FROM trades WHERE trade_date = ? ORDER BY trade_time ASC, id ASC",
            (trade_date,),
        ).fetchall()

    def save_strategy_trade(self, candidate: dict, source: dict) -> int | None:
        """Capture one deduplicated multi-leg strategy for paper validation."""
        now = datetime.now().isoformat(timespec="seconds")
        candle = str(source.get("candle_time") or now)
        structure_key = "|".join(
            f"{leg['action']}:{leg['option_type']}:{float(leg['strike']):g}:{int(leg.get('lots', 1))}"
            for leg in candidate.get("legs", [])
        )
        self.cursor.execute(
            """INSERT OR IGNORE INTO strategy_trades
               (captured_at, trade_date, candle_time, symbol, expiry, strategy_name, friendly_name, family, bias,
                structure_key, legs_json, entry_spot, last_spot, max_profit, max_loss,
                capital_required, entry_cashflow, return_on_capital, market_regime,
                target_profit_amount, stop_loss_amount,
                breakevens_json, profit_zone, scenario_win_rate, rank_score, explanation, source_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, datetime.now().strftime("%d-%m-%Y"), candle, str(source.get("symbol") or ""),
             str(source.get("expiry") or ""), candidate["strategy"], candidate.get("friendly_name") or candidate["strategy"],
             candidate["family"], candidate["bias"],
             structure_key, json.dumps(candidate.get("legs") or [], default=str), float(source.get("spot") or 0),
             float(source.get("spot") or 0), float(candidate["max_profit"]), float(candidate["max_loss"]),
             float(candidate.get("capital_required") or 0), float(candidate.get("entry_cashflow") or 0),
             float(candidate.get("return_on_capital") or 0), str(source.get("market_regime") or "UNKNOWN"),
             float(source.get("strategy_target_profit_amount") or 0),
             float(source.get("strategy_stop_loss_amount") or 0),
             json.dumps(candidate.get("breakevens") or []), candidate.get("profit_zone", ""),
             float(candidate.get("scenario_profitable_percent") or 0), float(candidate.get("rank_score") or 0),
             candidate.get("explanation", ""), json.dumps(source, default=str)),
        )
        self.connection.commit()
        return int(self.cursor.lastrowid) if self.cursor.rowcount else None

    def update_strategy_trades(self, symbol: str, spot: float, candle_time: str = "", quote_rows=None, force_close=False) -> list[dict]:
        """Mark open paper strategies from live executable quotes and close exits."""
        from engine.strategy_portfolio_engine import payoff_at_expiry
        now = datetime.now()
        evaluation_time = now
        if candle_time:
            for parser in (
                lambda value: datetime.fromisoformat(value),
                lambda value: datetime.strptime(value, "%d-%m-%Y %H:%M"),
            ):
                try:
                    evaluation_time = parser(str(candle_time))
                    break
                except (TypeError, ValueError):
                    continue
        closed = []
        rows = self.cursor.execute(
            "SELECT * FROM strategy_trades WHERE status='OPEN' AND symbol=? ORDER BY id", (str(symbol).upper(),)
        ).fetchall()
        for row in rows:
            legs = json.loads(row["legs_json"] or "[]")
            live = {(str(q.get("symbol") or ""), str(q.get("option_type") or ""), float(q.get("strike") or 0)): q
                    for q in (quote_rows or [])}
            pnl = 0.0
            complete_mark = bool(live)
            for leg in legs:
                quote = live.get((str(leg.get("symbol") or ""), str(leg["option_type"]), float(leg["strike"])))
                if not quote:
                    complete_mark = False
                    break
                exit_price = float(quote.get("bid") or quote.get("ltp") or 0) if leg["action"] == "BUY" else float(quote.get("ask") or quote.get("ltp") or 0)
                if exit_price <= 0:
                    complete_mark = False
                    break
                multiplier = 1 if leg["action"] == "BUY" else -1
                pnl += (exit_price - float(leg["price"])) * int(leg["quantity"]) * multiplier
            pnl = round(pnl, 2) if complete_mark else payoff_at_expiry(legs, float(spot))
            # Limits are snapshotted on each capture.  One strategy reaching
            # its own boundary must never close unrelated open strategies.
            saved_target = float(row["target_profit_amount"] or 0)
            saved_stop = float(row["stop_loss_amount"] or 0)
            target = saved_target if saved_target > 0 else max(1.0, float(row["max_profit"]) * .50)
            loss_review = -saved_stop if saved_stop > 0 else -max(1.0, float(row["max_loss"]) * .50)
            outcome = None
            if pnl >= target:
                outcome = "TARGET BENEFIT REACHED"
            elif pnl <= loss_review:
                outcome = "LOSS REVIEW EXIT"
            elif force_close:
                outcome = "MARKET CLOSE EXIT"
            elif evaluation_time.strftime("%H:%M") >= "15:25":
                outcome = "TIME EXIT"
            review = ""
            if outcome:
                display_name = row["friendly_name"] or row["strategy_name"]
                review = (f"{display_name} ({row['strategy_name']}) automatically closed as {outcome}. "
                          f"Market moved from {float(row['entry_spot']):,.2f} to {float(spot):,.2f}; "
                          f"{'executable quote mark' if complete_mark else 'expiry-scenario fallback'} P&L ₹{pnl:,.2f}. " +
                          ("The saved payoff thesis worked in this observation." if pnl > 0 else
                           "The payoff thesis did not work; retain this result for future regime comparison."))
                self.cursor.execute(
                    "UPDATE strategy_trades SET last_spot=?, current_pnl=?, realized_pnl=?, status='CLOSED', outcome=?, exit_at=?, result_review=? WHERE id=?",
                    (float(spot), pnl, pnl, outcome, now.isoformat(timespec="seconds"), review, row["id"]),
                )
                closed.append({"id": row["id"], "strategy": display_name, "outcome": outcome, "pnl": pnl})
            else:
                self.cursor.execute("UPDATE strategy_trades SET last_spot=?, current_pnl=? WHERE id=?", (float(spot), pnl, row["id"]))
        self.connection.commit()
        return closed

    def get_strategy_daily_pnl(self, trade_date: str) -> dict:
        """Return combined realised plus current open paper-strategy P&L."""
        row = self.cursor.execute(
            """SELECT COUNT(*) total,
                      SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,
                      SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) closed_count,
                      COALESCE(SUM(CASE WHEN status='CLOSED' THEN realized_pnl ELSE current_pnl END), 0) combined_pnl
               FROM strategy_trades WHERE trade_date=?""",
            (trade_date,),
        ).fetchone()
        return dict(row)

    def close_strategy_trades_for_daily_limit(self, trade_date: str, outcome: str) -> list[dict]:
        """Close all open paper strategies at their latest verified marks."""
        now = datetime.now().isoformat(timespec="seconds")
        rows = self.cursor.execute(
            "SELECT * FROM strategy_trades WHERE trade_date=? AND status='OPEN' ORDER BY id",
            (trade_date,),
        ).fetchall()
        closed = []
        for row in rows:
            pnl = round(float(row["current_pnl"] or 0), 2)
            display_name = row["friendly_name"] or row["strategy_name"]
            review = (
                f"{display_name} ({row['strategy_name']}) automatically closed as {outcome}. "
                f"Latest verified paper mark P&L ₹{pnl:,.2f}. The combined daily strategy guard "
                "closed every open simulation and blocked fresh captures for this trading date. "
                "This is paper validation only; no broker order was placed."
            )
            self.cursor.execute(
                """UPDATE strategy_trades SET realized_pnl=current_pnl, status='CLOSED',
                          outcome=?, exit_at=?, result_review=? WHERE id=?""",
                (outcome, now, review, row["id"]),
            )
            closed.append({"id": row["id"], "strategy": display_name, "outcome": outcome, "pnl": pnl})
        self.connection.commit()
        return closed

    def save_strategy_session_review(self, trade_date: str, symbol: str, market_direction="UNKNOWN", market_regime="UNKNOWN") -> dict | None:
        """Persist one end-of-session review derived only from closed paper results."""
        rows = self.cursor.execute(
            "SELECT * FROM strategy_trades WHERE trade_date=? AND symbol=? AND status='CLOSED' ORDER BY realized_pnl DESC, id",
            (trade_date, str(symbol).upper()),
        ).fetchall()
        if not rows:
            return None
        wins = sum(float(row["realized_pnl"] or 0) > 0 for row in rows)
        losses = sum(float(row["realized_pnl"] or 0) < 0 for row in rows)
        flat = len(rows) - wins - losses
        best, worst = rows[0], rows[-1]
        best_name = best["friendly_name"] or best["strategy_name"]
        worst_name = worst["friendly_name"] or worst["strategy_name"]
        review = (
            f"Cutie closing review: {symbol} ka market {str(market_direction).upper()} direction aur "
            f"{str(market_regime).upper()} regime me raha. {len(rows)} defined-risk paper strategies me "
            f"{wins} profitable, {losses} loss aur {flat} flat rahe. Best: {best_name} "
            f"(₹{float(best['realized_pnl'] or 0):,.2f}); weakest: {worst_name} "
            f"(₹{float(worst['realized_pnl'] or 0):,.2f}). Same regime future me aaye to yeh result context hoga, entry guarantee nahi."
        )
        generated = datetime.now().isoformat(timespec="seconds")
        self.cursor.execute(
            """INSERT INTO strategy_session_reviews
               (trade_date, symbol, generated_at, market_direction, market_regime, total_strategies,
                wins, losses, flat, best_strategy, best_pnl, worst_strategy, worst_pnl, review_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date, symbol) DO UPDATE SET
                 generated_at=excluded.generated_at, market_direction=excluded.market_direction,
                 market_regime=excluded.market_regime, total_strategies=excluded.total_strategies,
                 wins=excluded.wins, losses=excluded.losses, flat=excluded.flat,
                 best_strategy=excluded.best_strategy, best_pnl=excluded.best_pnl,
                 worst_strategy=excluded.worst_strategy, worst_pnl=excluded.worst_pnl,
                 review_text=excluded.review_text""",
            (trade_date, str(symbol).upper(), generated, str(market_direction).upper(), str(market_regime).upper(),
             len(rows), wins, losses, flat, best_name, float(best["realized_pnl"] or 0),
             worst_name, float(worst["realized_pnl"] or 0), review),
        )
        self.connection.commit()
        return dict(self.cursor.execute(
            "SELECT * FROM strategy_session_reviews WHERE trade_date=? AND symbol=?", (trade_date, str(symbol).upper())
        ).fetchone())

    def finalize_open_strategy_sessions(self, trade_date: str) -> list[dict]:
        """Close every remaining paper strategy and persist one review per symbol.

        This is an end-of-session reconciliation fallback. It uses each symbol's
        last saved mark and never sends a broker order.
        """
        groups = self.cursor.execute(
            """SELECT symbol, MAX(last_spot) AS last_spot
               FROM strategy_trades WHERE trade_date=? AND status='OPEN'
               GROUP BY symbol""",
            (trade_date,),
        ).fetchall()
        results = []
        for group in groups:
            symbol = str(group["symbol"] or "").upper()
            spot = float(group["last_spot"] or 0)
            if not symbol or spot <= 0:
                continue
            closed = self.update_strategy_trades(symbol, spot, force_close=True)
            source = self.cursor.execute(
                """SELECT bias, market_regime FROM strategy_trades
                   WHERE trade_date=? AND symbol=? ORDER BY id DESC LIMIT 1""",
                (trade_date, symbol),
            ).fetchone()
            review = self.save_strategy_session_review(
                trade_date, symbol,
                str(source["bias"] or "UNKNOWN") if source else "UNKNOWN",
                str(source["market_regime"] or "UNKNOWN") if source else "UNKNOWN",
            )
            results.append({"symbol": symbol, "closed": closed, "review": review})
        # Also backfill a missing review when trades were already closed by the
        # normal 15:25 exit before the review timer ran.
        symbols = self.cursor.execute(
            "SELECT DISTINCT symbol FROM strategy_trades WHERE trade_date=? AND status='CLOSED'", (trade_date,)
        ).fetchall()
        reviewed = {str(row["symbol"]) for row in self.get_strategy_session_reviews(5000) if str(row["trade_date"]) == trade_date}
        for item in symbols:
            symbol = str(item["symbol"] or "").upper()
            if symbol and symbol not in reviewed:
                source = self.cursor.execute(
                    "SELECT bias, market_regime FROM strategy_trades WHERE trade_date=? AND symbol=? ORDER BY id DESC LIMIT 1",
                    (trade_date, symbol),
                ).fetchone()
                review = self.save_strategy_session_review(
                    trade_date, symbol,
                    str(source["bias"] or "UNKNOWN"), str(source["market_regime"] or "UNKNOWN"),
                )
                results.append({"symbol": symbol, "closed": [], "review": review})
        return results

    def get_strategy_session_reviews(self, limit=100) -> list[sqlite3.Row]:
        return self.cursor.execute(
            "SELECT * FROM strategy_session_reviews ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 1000)),)
        ).fetchall()

    def get_strategy_trades(self, trade_date: str | None = None, limit: int = 1000) -> list[sqlite3.Row]:
        query, values = "SELECT * FROM strategy_trades", []
        if trade_date:
            query += " WHERE trade_date=?"; values.append(trade_date)
        query += " ORDER BY id DESC LIMIT ?"; values.append(max(1, min(int(limit), 5000)))
        return self.cursor.execute(query, values).fetchall()

    def get_strategy_trade_summary(self) -> dict:
        row = self.cursor.execute(
            """SELECT COUNT(*) total, SUM(status='OPEN') open_count, SUM(status='CLOSED') closed_count,
                      SUM(CASE WHEN status='CLOSED' AND realized_pnl>0 THEN 1 ELSE 0 END) wins,
                      SUM(CASE WHEN status='CLOSED' AND realized_pnl<=0 THEN 1 ELSE 0 END) losses,
                      COALESCE(SUM(CASE WHEN status='CLOSED' THEN realized_pnl ELSE 0 END),0) pnl
               FROM strategy_trades"""
        ).fetchone()
        return dict(row)

    def get_strategy_performance(self) -> list[dict]:
        """Rank actual outcomes and attach conservative validation evidence."""
        from engine.performance_calibration import calibrate_outcomes

        rows = self.cursor.execute(
            """SELECT strategy_name, COALESCE(friendly_name, strategy_name) friendly_name,
                      GROUP_CONCAT(DISTINCT COALESCE(market_regime, 'UNKNOWN')) market_regimes,
                      ROUND(AVG(return_on_capital), 2) average_model_roc,
                      ROUND(AVG(capital_required), 2) average_capital_required,
                      COUNT(DISTINCT trade_date) independent_sessions
               FROM strategy_trades WHERE status='CLOSED'
               GROUP BY strategy_name, friendly_name"""
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            pnl_rows = self.cursor.execute(
                "SELECT realized_pnl FROM strategy_trades WHERE status='CLOSED' AND strategy_name=? AND COALESCE(friendly_name, strategy_name)=?",
                (item["strategy_name"], item["friendly_name"]),
            ).fetchall()
            item.update(calibrate_outcomes([value["realized_pnl"] for value in pnl_rows]))
            item["average_pnl"] = item["expectancy"]
            result.append(item)
        tier_rank = {"VALIDATED LOW-RISK": 0, "PAPER VALIDATION": 1, "PAPER ONLY": 2,
                     "UNPROVEN": 3, "REJECTED BY EVIDENCE": 4}
        return sorted(result, key=lambda x: (
            tier_rank.get(x["validation_tier"], 9), -x["wilson_lower_bound"],
            -x["profit_factor"], -x["expectancy"], -x["samples"], x["strategy_name"],
        ))

    def get_paper_outcome_quality(self, limit: int = 500) -> list[dict]:
        """Return the complete timing/execution/excursion dataset used for post-mortem review."""
        rows = self.cursor.execute(
            """SELECT t.id, t.trade_date, t.trade_time, t.symbol, t.option_type, t.entry, t.exit,
                      t.stoploss, t.target, t.outcome, t.pnl, t.setup, t.created_at, t.closed_at,
                      p.contract_symbol, p.initial_stoploss, p.entry_lateness_seconds,
                      p.premium_spread_percent, p.initial_atr, p.mae, p.mfe, p.min_ltp, p.max_ltp,
                      p.plan_json
               FROM trades t JOIN paper_trade_links p ON p.trade_id=t.id
               ORDER BY t.id DESC LIMIT ?""",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            entry = float(row["entry"] or 0)
            minimum = row["min_ltp"]
            maximum = row["max_ltp"]
            value["mae"] = float(row["mae"]) if row["mae"] is not None else round(max(0.0, entry - float(minimum)), 2) if minimum is not None else None
            value["mfe"] = float(row["mfe"]) if row["mfe"] is not None else round(max(0.0, float(maximum) - entry), 2) if maximum is not None else None
            value["risk_points"] = round(entry - float(row["initial_stoploss"] or row["stoploss"] or 0), 2)
            value["mae_r"] = round(float(value["mae"]) / value["risk_points"], 2) if value["mae"] is not None and value["risk_points"] > 0 else None
            value["mfe_r"] = round(float(value["mfe"]) / value["risk_points"], 2) if value["mfe"] is not None and value["risk_points"] > 0 else None
            result.append(value)
        return result

    def save_post_market_tps_analysis(self, analysis: dict) -> int:
        """Create or refresh one permanent date-wise TPS post-market note."""
        values = (
            str(analysis["trade_date"]),
            str(analysis["generated_at"]),
            str(analysis.get("title") or "Post Market Analysis of TPS"),
            str(analysis["summary_text"]),
            json.dumps(analysis.get("metrics") or {}, ensure_ascii=False, default=str),
        )
        self.cursor.execute(
            """
            INSERT INTO post_market_tps_analysis
                (trade_date, generated_at, title, summary_text, metrics_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(trade_date) DO UPDATE SET
                generated_at = excluded.generated_at,
                title = excluded.title,
                summary_text = excluded.summary_text,
                metrics_json = excluded.metrics_json
            """,
            values,
        )
        self.connection.commit()
        row = self.cursor.execute(
            "SELECT id FROM post_market_tps_analysis WHERE trade_date = ?",
            (values[0],),
        ).fetchone()
        return int(row["id"])

    def get_market_snapshot_dates(self) -> list[sqlite3.Row]:
        return self.cursor.execute(
            """SELECT trade_date, symbol, COUNT(*) AS snapshot_count
               FROM market_snapshots WHERE LOWER(timeframe) = '5m'
               GROUP BY trade_date, symbol ORDER BY MAX(captured_at) DESC"""
        ).fetchall()

    def get_market_snapshots_for_symbol(self, trade_date: str, symbol: str) -> list[sqlite3.Row]:
        return self.cursor.execute(
            """SELECT * FROM market_snapshots WHERE trade_date = ? AND symbol = ?
               ORDER BY captured_at ASC, timeframe ASC""",
            (trade_date, str(symbol).upper()),
        ).fetchall()

    def save_daily_trend_memory(self, memory: dict) -> int:
        values = (
            memory["trade_date"], str(memory["symbol"]).upper(),
            memory.get("generated_at") or datetime.now().isoformat(timespec="seconds"),
            memory["trend"], memory["chart_pattern"], memory["candle_signature"],
            memory["session_open"], memory["session_high"], memory["session_low"], memory["session_close"],
            memory["return_pct"], memory["range_pct"], memory["snapshot_count"], memory["outcome_text"],
            json.dumps(memory.get("features") or {}, ensure_ascii=False),
        )
        self.cursor.execute(
            """INSERT INTO daily_trend_memory
               (trade_date, symbol, generated_at, trend, chart_pattern, candle_signature,
                session_open, session_high, session_low, session_close, return_pct, range_pct,
                snapshot_count, outcome_text, features_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date, symbol) DO UPDATE SET
                generated_at=excluded.generated_at, trend=excluded.trend, chart_pattern=excluded.chart_pattern,
                candle_signature=excluded.candle_signature, session_open=excluded.session_open,
                session_high=excluded.session_high, session_low=excluded.session_low,
                session_close=excluded.session_close, return_pct=excluded.return_pct, range_pct=excluded.range_pct,
                snapshot_count=excluded.snapshot_count, outcome_text=excluded.outcome_text,
                features_json=excluded.features_json""",
            values,
        )
        self.connection.commit()
        row = self.cursor.execute(
            "SELECT id FROM daily_trend_memory WHERE trade_date = ? AND symbol = ?",
            (values[0], values[1]),
        ).fetchone()
        return int(row["id"])

    def get_daily_trend_memories(self, symbol: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
        if symbol:
            return self.cursor.execute(
                "SELECT * FROM daily_trend_memory WHERE symbol = ? ORDER BY generated_at DESC LIMIT ?",
                (str(symbol).upper(), int(limit)),
            ).fetchall()
        return self.cursor.execute(
            "SELECT * FROM daily_trend_memory ORDER BY generated_at DESC LIMIT ?", (int(limit),)
        ).fetchall()

    def get_post_market_tps_analysis(self, trade_date: str) -> sqlite3.Row | None:
        return self.cursor.execute(
            "SELECT * FROM post_market_tps_analysis WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()

    def get_post_market_tps_analyses(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.cursor.execute(
            """
            SELECT * FROM post_market_tps_analysis
            ORDER BY substr(trade_date, 7, 4) || substr(trade_date, 4, 2) || substr(trade_date, 1, 2) DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 5000)),),
        ).fetchall()

    def get_post_market_source_dates(self) -> list[str]:
        """Return dates which contain attempts, trades, or saved market data."""
        rows = self.cursor.execute(
            """
            SELECT trade_date FROM auto_trade_attempts
            UNION SELECT trade_date FROM trades
            UNION SELECT trade_date FROM market_snapshots
            """
        ).fetchall()
        valid_dates = []
        for row in rows:
            value = str(row["trade_date"] or "")
            try:
                datetime.strptime(value, "%d-%m-%Y")
            except ValueError:
                continue
            valid_dates.append(value)
        return sorted(valid_dates, key=lambda value: datetime.strptime(value, "%d-%m-%Y"), reverse=True)

    def export_auto_trade_attempts(self, destination: str | Path, trade_date: str | None = None) -> int:
        rows = self.get_auto_trade_attempts(trade_date, limit=5000)
        headers = (
            "checked_at", "candle_time", "trade_date", "symbol", "future_symbol", "outcome", "decision",
            "candidate", "confirmations_passed", "confirmations_total", "score", "trade_id", "status_text",
            "primary_blocker", "secondary_warnings_json", "evidence_states_json", "source_completeness_json",
            "signal_discovered_at", "first_valid_trigger_at", "final_capture_at", "timing_delay_seconds",
            "timing_stage", "details_json",
        )
        with Path(destination).open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(tuple(row[header] for header in headers) for row in rows)
        return len(rows)

    def get_open_trades(self, symbol: str | None = None) -> list[sqlite3.Row]:
        query, values = "SELECT * FROM trades WHERE status = 'OPEN'", ()
        if symbol:
            query += " AND symbol = ?"
            values = (str(symbol).upper(),)
        return self.cursor.execute(query + " ORDER BY id DESC", values).fetchall()

    def has_open_trade(self, symbol: str) -> bool:
        return bool(self.get_open_trades(symbol))

    def evaluate_open_trade_alerts(self, symbol: str) -> list[dict]:
        """Evaluate the latest 5m/15m saved snapshots and persist new review alerts."""
        from engine.open_trade_guard import evaluate_open_trade

        snapshots = self.get_market_snapshots()
        latest = {
            timeframe: next((row for row in snapshots if row["symbol"] == str(symbol).upper() and row["timeframe"] == timeframe), None)
            for timeframe in ("5m", "15m")
        }
        if not all(latest.values()):
            return []
        alerts = []
        for trade in self.get_open_trades(symbol):
            alert = evaluate_open_trade(trade, latest["5m"], latest["15m"])
            if not alert:
                continue
            result = self.cursor.execute(
                "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                (alert["trade_id"], datetime.now().isoformat(timespec="seconds"), alert["alert_type"], alert["title"], alert["message"]),
            )
            if result.rowcount:
                alerts.append(alert)
        self.connection.commit()
        return alerts

    def get_day_summary(self, trade_date: str) -> dict[str, float | int]:
        """Return the recorded-trade metrics for the supplied journal date."""
        row = self.cursor.execute(
            """
            SELECT COUNT(*) AS trades, COALESCE(SUM(pnl), 0) AS pnl
            FROM trades WHERE trade_date = ?
            """,
            (trade_date,),
        ).fetchone()
        return {"trades": int(row["trades"]), "pnl": round(float(row["pnl"]), 2)}

    def close(self) -> None:
        self.connection.close()
