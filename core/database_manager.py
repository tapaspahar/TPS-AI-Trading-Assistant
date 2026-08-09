"""SQLite persistence for the TPS trade journal."""

from __future__ import annotations

import sqlite3
import csv
import json
import os
import shutil
from datetime import datetime
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
                last_alert_level TEXT
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
        for name, definition in (("last_ltp", "REAL"), ("min_ltp", "REAL"), ("max_ltp", "REAL"), ("last_alert_level", "TEXT")):
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
        self.connection.commit()

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
        values = (
            trade.trade_date, trade.trade_time, trade.market, trade.symbol.upper(),
            trade.expiry, trade.strike, trade.option, trade.entry, 0.0,
            trade.stoploss, trade.target, trade.quantity, 0.0, 0.0, trade.setup,
            int(trade.trend), int(trade.vwap), int(trade.ema), int(trade.volume), int(trade.oi),
            trade.psychology_before, trade.psychology_after, trade.mistake, trade.confidence,
            analysis["score"], analysis["decision"], ", ".join(analysis["reasons"]) or "No technical confirmations recorded.",
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
            notes="TPS PAPER TRADE: automatically monitored from Angel One option LTP; no broker order was sent.",
        )
        trade_id = self.save_open_trade(trade)
        self.cursor.execute(
            "INSERT INTO paper_trade_links (trade_id, exchange, token, contract_symbol) VALUES (?, ?, ?, ?)",
            (trade_id, str(contract["exchange"]), str(contract["token"]), str(contract["symbol"])),
        )
        self.connection.commit()
        return trade_id

    def monitor_paper_trades(self, client) -> list[dict]:
        """Close simulated trades on a verified option quote only; no order API is used."""
        rows = self.cursor.execute(
            """SELECT t.*, p.exchange, p.token, p.contract_symbol, p.last_ltp, p.min_ltp, p.max_ltp, p.last_alert_level FROM trades t
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
            risk = max(float(row["entry"]) - float(row["stoploss"]), 0.000001)
            loss_progress = (float(row["entry"]) - ltp) / risk
            alert_level = "CRITICAL" if loss_progress >= .90 else "STRONG" if loss_progress >= .75 else "EARLY" if loss_progress >= .50 else None
            self.cursor.execute(
                "UPDATE paper_trade_links SET last_ltp = ?, min_ltp = ?, max_ltp = ?, last_alert_level = COALESCE(?, last_alert_level) WHERE trade_id = ?",
                (ltp, minimum, maximum, alert_level, int(row["id"])),
            )
            if alert_level:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO trade_alerts (trade_id, created_at, alert_type, title, message) VALUES (?, ?, ?, ?, ?)",
                    (int(row["id"]), datetime.now().isoformat(timespec="seconds"), f"PREMIUM_SL_{alert_level}",
                     f"{alert_level.title()} option-premium stop warning",
                     f"{row['contract_symbol']} LTP {ltp:.2f}; stop {float(row['stoploss']):.2f}; "
                     f"{max(0, loss_progress) * 100:.0f}% of entry-to-stop risk used."),
                )
            outcome = "TARGET HIT" if ltp >= float(row["target"]) else "STOP LOSS HIT" if ltp <= float(row["stoploss"]) else None
            if outcome and self.close_trade(int(row["id"]), ltp, outcome):
                closed.append({"trade_id": int(row["id"]), "symbol": row["contract_symbol"], "ltp": ltp, "outcome": outcome})
        self.connection.commit()
        return closed

    def get_paper_trade_monitoring(self) -> list[dict]:
        """Return live premium, MAE/MFE and active stop-proximity alerts."""
        rows = self.cursor.execute(
            """SELECT t.id, t.entry, t.stoploss, t.target, p.contract_symbol, p.last_ltp,
                      p.min_ltp, p.max_ltp, p.last_alert_level
               FROM trades t JOIN paper_trade_links p ON p.trade_id = t.id
               WHERE t.status = 'OPEN' ORDER BY t.id DESC"""
        ).fetchall()
        return [{
            "trade_id": int(row["id"]), "symbol": row["contract_symbol"], "ltp": row["last_ltp"],
            "mae": round(float(row["entry"]) - float(row["min_ltp"]), 2) if row["min_ltp"] is not None else 0,
            "mfe": round(float(row["max_ltp"]) - float(row["entry"]), 2) if row["max_ltp"] is not None else 0,
            "alert": row["last_alert_level"], "stoploss": float(row["stoploss"]), "target": float(row["target"]),
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
                       SUM(CASE WHEN t.status = 'CLOSED' AND t.outcome = 'STOP LOSS HIT' THEN 1 ELSE 0 END) AS stoploss_hits
                FROM trades t JOIN paper_trade_links p ON p.trade_id = t.id {where}""", values,
        ).fetchone()
        return {key: int(row[key] or 0) for key in ("trades", "days", "open_trades", "target_hits", "stoploss_hits")}

    def close_trade(self, trade_id: int, exit_price: float, outcome: str = "MANUAL EXIT") -> bool:
        """Record the actual exit for one previously saved open trade."""
        if exit_price <= 0:
            raise ValueError("Enter an actual exit price greater than zero.")
        outcome = str(outcome).upper()
        if outcome not in {"TARGET HIT", "STOP LOSS HIT", "MANUAL EXIT"}:
            raise ValueError("Choose Target Hit, Stop Loss Hit, or Manual Exit.")
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
