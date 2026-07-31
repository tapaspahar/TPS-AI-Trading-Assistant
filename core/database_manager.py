import sqlite3


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

            symbol TEXT,

            option_type TEXT,

            entry REAL,
            exit REAL,

            quantity INTEGER,

            pnl REAL,

            psychology TEXT,

            screenshot TEXT

        )
        """)

        self.connection.commit()

    def save_trade(
        self,
        trade_date,
        trade_time,
        symbol,
        strike,
        option_type,
        entry,
        exit,
        quantity,
        psychology
    ):

        pnl = (float(exit) - float(entry)) * int(quantity)

        self.cursor.execute("""
        INSERT INTO trades(
            trade_date,
            trade_time,
            symbol,
            option_type,
            entry,
            exit,
            quantity,
            pnl,
            psychology,
            screenshot
        )

        VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            trade_date,
            trade_time,
            symbol,
            f"{strike} {option_type}",
            entry,
            exit,
            quantity,
            pnl,
            psychology,
            ""
        ))

        self.connection.commit()

    def get_all_trades(self):

        self.cursor.execute("""
        SELECT
            trade_date,
            trade_time,
            symbol,
            option_type,
            entry,
            exit,
            quantity,
            pnl,
            psychology
        FROM trades
        ORDER BY id DESC
        """)

        return self.cursor.fetchall()

    def close(self):

        self.connection.close()