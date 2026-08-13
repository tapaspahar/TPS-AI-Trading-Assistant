"""SQLite persistence for the TPS trade journal."""

from __future__ import annotations

import sqlite3
import csv
import json
import os
import shutil
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
        self.create_tables()

    def create_tables(self) -> None:
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
                                 ("initial_stoploss", "REAL"), ("trailing_stoploss", "REAL"), ("plan_json", "TEXT")):
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
        self.connection.commit()

    def save_notification(
        self, category: str, title: str, message: str, created_at: str | None = None
    ) -> int:
        """Persist one desktop alert so its history survives application updates."""
        timestamp = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
        result = self.cursor.execute(
            "INSERT INTO notifications (created_at, category, title, message) VALUES (?, ?, ?, ?)",
            (timestamp, str(category), str(title), str(message)),
        )
        self.connection.commit()
        return int(result.lastrowid)

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
                   AND substr(captured_at, 12, 5) BETWEEN '09:15' AND '09:25'
                   ORDER BY captured_at ASC, id ASC""",
                (row["symbol"],),
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
               (trade_id, exchange, token, contract_symbol, initial_stoploss, trailing_stoploss, plan_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, str(contract["exchange"]), str(contract["token"]), str(contract["symbol"]),
             float(plan["stoploss"]), float(plan["stoploss"]), json.dumps(plan, ensure_ascii=False, default=str)),
        )
        self.cursor.execute(
            "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
            (trade_id, datetime.now().isoformat(timespec="seconds"), "PAPER_ENTRY", "Paper trade captured",
             f"{contract['symbol']} entry {float(plan['entry']):.2f}; stop {float(plan['stoploss']):.2f}; target {float(plan['target']):.2f}."),
        )
        self.connection.commit()
        return trade_id

    def monitor_paper_trades(self, client, settings=None, now=None) -> list[dict]:
        """Close simulated trades on a verified option quote only; no order API is used."""
        from core.market_session import IST, MARKET_CLOSE
        from datetime import timedelta

        settings = settings or {}
        now = now or datetime.now(IST)
        now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
        rows = self.cursor.execute(
            """SELECT t.*, p.exchange, p.token, p.contract_symbol, p.last_ltp, p.min_ltp, p.max_ltp,
                      p.last_alert_level, p.initial_stoploss, p.trailing_stoploss FROM trades t
               JOIN paper_trade_links p ON p.trade_id = t.id WHERE t.status = 'OPEN'"""
        ).fetchall()
        closed = []
        for row in rows:
            quote = client.get_option_quote(row["exchange"], row["token"])
            ltp = float(quote.get("ltp", 0) or 0)
            if ltp <= 0:
                continue
            minimum = min(ltp, float(row["min_ltp"])) if row["min_ltp"] is not None else ltp
            maximum = max(ltp, float(row["max_ltp"])) if row["max_ltp"] is not None else ltp
            initial_stop = float(row["initial_stoploss"] if row["initial_stoploss"] is not None else row["stoploss"])
            active_stop = float(row["trailing_stoploss"] if row["trailing_stoploss"] is not None else row["stoploss"])
            risk = max(float(row["entry"]) - initial_stop, 0.000001)
            if settings.get("trailing_stop_enabled", True) and maximum >= float(row["entry"]) + float(settings.get("trailing_stop_trigger_r", 1)) * risk:
                active_stop = max(active_stop, float(row["entry"]) + float(settings.get("trailing_stop_lock_r", .25)) * risk)
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
                          last_alert_level = COALESCE(?, last_alert_level), trailing_stoploss = ? WHERE trade_id = ?""",
                (ltp, minimum, maximum, alert_level, active_stop, int(row["id"])),
            )
            if alert_level:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                    (int(row["id"]), datetime.now().isoformat(timespec="seconds"), f"PREMIUM_SL_{alert_level}",
                     f"{alert_level.title()} option-premium stop warning",
                     f"{row['contract_symbol']} LTP {ltp:.2f}; active stop {active_stop:.2f}; "
                     f"{max(0, loss_progress) * 100:.0f}% of entry-to-stop risk used."),
                )
            close_at = datetime.combine(now.date(), MARKET_CLOSE, IST)
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
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.outcome IN ('STOP LOSS HIT','TRAILING STOP HIT') THEN 1 ELSE 0 END) AS stoploss_hits
                FROM trades t JOIN paper_trade_links p ON p.trade_id = t.id {where}""", values,
        ).fetchone()
        result = {key: int(row[key] or 0) for key in ("trades", "days", "open_trades", "target_hits", "stoploss_hits")}
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
        pnl = round((float(exit_price) - float(row["entry"])) * int(row["quantity"]), 2)
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
                 f"Paper trade closed: {outcome}", f"Exit {float(exit_price):.2f}; P&L {pnl:.2f}; R:R {rr_ratio:.2f}."),
            )
        self.connection.commit()
        if closed:
            self.cursor.execute("UPDATE trade_alerts SET status = 'RESOLVED' WHERE trade_id = ? AND status = 'ACTIVE'", (int(trade_id),))
            self.connection.commit()
        return closed

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
        checked_at = str(attempt.get("checked_at") or datetime.now().isoformat(timespec="seconds"))
        candle_time = attempt.get("candle_time")
        outcome = "TRADE CAPTURED" if result.get("plan") else "NO TRADE" if chart else "RETRY PENDING" if result.get("retry_pending") else "SKIPPED"
        values = (
            checked_at, candle_time, datetime.fromisoformat(checked_at).strftime("%d-%m-%Y"), str(symbol).upper(),
            attempt.get("future_symbol"), outcome, chart.get("decision"), attempt.get("candidate"),
            strategy.get("passed"), strategy.get("total", 6) if strategy else None, chart.get("score"),
            result.get("trade_id"), result.get("status", "Auto paper cycle completed"),
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
                          trade_id = ?, status_text = ?, details_json = ? WHERE id = ?""",
                (values[0], values[2], values[4], values[5], values[6], values[7], values[8], values[9], values[10], values[11], values[12], values[13], existing["id"]),
            )
            self.connection.commit()
            return True
        result_row = self.cursor.execute(
            """INSERT INTO auto_trade_attempts (
                   checked_at, candle_time, trade_date, symbol, future_symbol, outcome, decision, candidate,
                   confirmations_passed, confirmations_total, score, trade_id, status_text, details_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        self.connection.commit()
        return result_row.rowcount == 1

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
        headers = ("checked_at", "candle_time", "trade_date", "symbol", "future_symbol", "outcome", "decision", "candidate", "confirmations_passed", "confirmations_total", "score", "trade_id", "status_text", "details_json")
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
