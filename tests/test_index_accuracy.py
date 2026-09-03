import tempfile
from pathlib import Path

from core.database_manager import Database
from services.index_accuracy import index_accuracy_profiles


def test_index_accuracy_is_separate_and_uses_only_closed_captures():
    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder) / "index-accuracy.db")
        try:
            for symbol, pnl, status in (("NIFTY", 100, "CLOSED"), ("NIFTY", -50, "CLOSED"), ("BANKNIFTY", 75, "CLOSED"), ("SENSEX", 0, "OPEN")):
                trade_id = db.save_paper_trade({
                    "underlying": symbol, "entry": 10, "stoploss": 8, "target": 14,
                    "quantity": 1, "confidence": 95, "option_type": "CE",
                    "contract": {"expiry": "2026-09-03", "strike": 100, "exchange": "NFO", "token": symbol, "symbol": f"{symbol}TESTCE"},
                })
                db.cursor.execute(
                    "UPDATE trades SET trade_date='03-09-2026', symbol=?, status=?, pnl=? WHERE id=?",
                    (symbol, status, pnl, trade_id),
                )
                db.cursor.execute(
                    """INSERT INTO auto_trade_attempts
                       (checked_at,trade_date,symbol,outcome,score,trade_id,status_text,details_json)
                       VALUES ('2026-09-03T10:05:00','03-09-2026',?,'CAPTURED',95,?,'captured','{}')""",
                    (symbol, trade_id),
                )
            db.cursor.execute(
                """INSERT INTO auto_trade_attempts
                   (checked_at,trade_date,symbol,outcome,score,status_text,details_json)
                   VALUES ('2026-09-03T10:10:00','03-09-2026','BANKNIFTY','STRATEGY REJECT',40,'reject','{}')"""
            )
            db.connection.commit()
            profiles = index_accuracy_profiles(db, "03-09-2026")
            assert profiles["NIFTY"]["closed"] == 2
            assert profiles["NIFTY"]["win_rate"] == 50.0
            assert profiles["NIFTY"]["expectancy"] == 25.0
            assert profiles["BANKNIFTY"]["attempts"] == 2
            assert profiles["BANKNIFTY"]["win_rate"] == 100.0
            assert profiles["SENSEX"]["closed"] == 0
            assert profiles["SENSEX"]["confidence"] == "LOW SAMPLE"
        finally:
            db.close()
