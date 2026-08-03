"""SQLite persistence for the TPS trade journal."""

from __future__ import annotations

import sqlite3
import csv
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
        default_path = Path(__file__).resolve().parents[1] / "database" / "tps_ai.db"
        self.db_path = Path(db_path) if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                created_at TEXT NOT NULL
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
            datetime.now().isoformat(timespec="seconds"),
        )
        self.cursor.execute(
            """
            INSERT INTO trades (
                trade_date, trade_time, market, symbol, expiry, strike, option_type,
                entry, exit, stoploss, target, quantity, pnl, rr_ratio, setup,
                trend, vwap, ema, volume, oi, psychology_before, psychology_after,
                mistake, confidence, ai_score, ai_decision, ai_review, notes,
                screenshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.connection.commit()
        return int(self.cursor.lastrowid)

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
            SELECT id, trade_date, trade_time, symbol, strike, option_type, entry, stoploss, target, exit,
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
                   entry, exit, stoploss, target, quantity, pnl, rr_ratio, setup,
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
