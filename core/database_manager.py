import sqlite3
from datetime import datetime


class Database:

    def __init__(self):

        print("Database Connected Successfully")

        self.connection = sqlite3.connect("database/tps_ai.db")

        self.cursor = self.connection.cursor()

        self.create_tables()

    def create_tables(self):

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            trade_date TEXT,
            trade_time TEXT,

            market TEXT,

            symbol TEXT,

            expiry TEXT,

            strike TEXT,

            option_type TEXT,

            entry REAL,
            exit REAL,

            stoploss REAL,
            target REAL,

            quantity INTEGER,

            pnl REAL,

            rr_ratio REAL,

            setup TEXT,

            trend INTEGER,
            vwap INTEGER,
            ema INTEGER,
            volume INTEGER,
            oi INTEGER,

            psychology_before TEXT,
            psychology_after TEXT,

            mistake TEXT,

            confidence INTEGER,

            ai_score INTEGER,

            ai_decision TEXT,

            ai_review TEXT,

            notes TEXT,

            screenshot TEXT,

            created_at TEXT

        )
        """)

        self.connection.commit()

    def save_trade(
        self,
        trade_date,
        trade_time,
        market,
        symbol,
        expiry,
        strike,
        option_type,
        entry,
        exit,
        stoploss,
        target,
        quantity,
        setup,
        trend,
        vwap,
        ema,
        volume,
        oi,
        psychology_before,
        psychology_after,
        mistake,
        confidence,
        notes,
        screenshot=""
    ):

        pnl = (float(exit) - float(entry)) * int(quantity)

        risk = abs(float(entry) - float(stoploss))

        reward = abs(float(target) - float(entry))

        rr_ratio = round(reward / risk, 2) if risk > 0 else 0

        self.cursor.execute("""
        INSERT INTO trades(

            trade_date,
            trade_time,

            market,

            symbol,

            expiry,

            strike,

            option_type,

            entry,
            exit,

            stoploss,
            target,

            quantity,

            pnl,

            rr_ratio,

            setup,

            trend,
            vwap,
            ema,
            volume,
            oi,

            psychology_before,
            psychology_after,

            mistake,

            confidence,

            ai_score,

            ai_decision,

            ai_review,

            notes,

            screenshot,

            created_at

        )

        VALUES(
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,?
        )
        """, (

            trade_date,
            trade_time,

            market,

            symbol,

            expiry,

            strike,

            option_type,

            entry,
            exit,

            stoploss,
            target,

            quantity,

            pnl,

            rr_ratio,

            setup,

            int(trend),
            int(vwap),
            int(ema),
            int(volume),
            int(oi),

            psychology_before,
            psychology_after,

            mistake,

            confidence,

            0,

            "",

            "",

            notes,

            screenshot,

            datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        ))

        self.connection.commit()

    def get_all_trades(self):

        self.cursor.execute("""

        SELECT

            trade_date,
            trade_time,

            market,

            symbol,

            strike,

            option_type,

            entry,

            exit,

            quantity,

            pnl,

            rr_ratio,

            psychology_before,

            confidence

        FROM trades

        ORDER BY id DESC

        """)

        return self.cursor.fetchall()

    def close(self):

        self.connection.close()