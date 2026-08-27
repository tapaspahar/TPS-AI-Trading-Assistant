"""Upgrade-safe persistence for expiry observations and spike events."""
import json
from core.database_manager import Database


class ExpiryObservationStore:
    def __init__(self, db=None):
        self.db = db or Database()
        self.db.cursor.execute("""CREATE TABLE IF NOT EXISTS expiry_option_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT NOT NULL, trade_date TEXT NOT NULL,
            underlying TEXT NOT NULL, expiry TEXT NOT NULL, contract_symbol TEXT NOT NULL,
            strike REAL NOT NULL, option_type TEXT NOT NULL, moneyness TEXT NOT NULL, atm_distance REAL NOT NULL,
            spot REAL NOT NULL, premium REAL NOT NULL, premium_change_pct REAL, volume REAL, volume_ratio REAL,
            open_interest REAL, oi_change REAL, oi_change_pct REAL, underlying_move REAL,
            iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL, sustain_seconds INTEGER NOT NULL DEFAULT 0,
            cas_context TEXT NOT NULL, source_completeness TEXT NOT NULL, details_json TEXT NOT NULL,
            UNIQUE(observed_at, contract_symbol))""")
        self.db.cursor.execute("""CREATE TABLE IF NOT EXISTS expiry_spike_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT NOT NULL UNIQUE, trade_date TEXT NOT NULL,
            started_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL, strike REAL NOT NULL, option_type TEXT NOT NULL,
            moneyness TEXT NOT NULL, premium REAL NOT NULL, peak_change_pct REAL NOT NULL,
            volume_ratio REAL, oi_change_pct REAL, spot REAL NOT NULL, duration_seconds INTEGER NOT NULL DEFAULT 0,
            cas_context TEXT NOT NULL, source_completeness TEXT NOT NULL, event_text TEXT NOT NULL,
            details_json TEXT NOT NULL)""")
        additions = {
            "spike_start_premium": "REAL", "spike_event_premium": "REAL", "spike_latest_premium": "REAL",
            "opposite_contract_symbol": "TEXT", "opposite_option_type": "TEXT",
            "opposite_start_premium": "REAL", "opposite_event_premium": "REAL", "opposite_latest_premium": "REAL",
            "opposite_change_pct": "REAL", "paired_last_updated_at": "TEXT",
        }
        existing = {row[1] for row in self.db.cursor.execute("PRAGMA table_info(expiry_spike_events)").fetchall()}
        for name, sql_type in additions.items():
            if name not in existing:
                self.db.cursor.execute(f"ALTER TABLE expiry_spike_events ADD COLUMN {name} {sql_type}")
        self.db.connection.commit()

    def save_observation(self, row):
        columns = ("observed_at trade_date underlying expiry contract_symbol strike option_type moneyness atm_distance spot premium "
                   "premium_change_pct volume volume_ratio open_interest oi_change oi_change_pct underlying_move iv delta gamma theta vega "
                   "sustain_seconds cas_context source_completeness details_json").split()
        values = [row.get(name) for name in columns[:-1]] + [json.dumps(row, default=str)]
        self.db.cursor.execute(f"INSERT OR IGNORE INTO expiry_option_observations ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
        self.db.connection.commit()

    def save_event(self, row):
        columns = ("event_key trade_date started_at last_seen_at underlying contract_symbol strike option_type moneyness premium peak_change_pct "
                   "volume_ratio oi_change_pct spot duration_seconds cas_context source_completeness event_text "
                   "spike_start_premium spike_event_premium spike_latest_premium opposite_contract_symbol opposite_option_type "
                   "opposite_start_premium opposite_event_premium opposite_latest_premium opposite_change_pct paired_last_updated_at details_json").split()
        values = [row.get(name) for name in columns[:-1]] + [json.dumps(row, default=str)]
        self.db.cursor.execute(f"INSERT OR REPLACE INTO expiry_spike_events ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
        self.db.connection.commit()

    def events(self, limit=250):
        return [dict(row) for row in self.db.cursor.execute("SELECT * FROM expiry_spike_events ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]

    def observations(self, trade_date, underlying, limit=500):
        return [dict(row) for row in self.db.cursor.execute(
            "SELECT * FROM expiry_option_observations WHERE trade_date=? AND underlying=? ORDER BY observed_at DESC LIMIT ?",
            (trade_date, underlying, limit)).fetchall()]

    def historical_observations(self, underlying, limit=10000):
        return [dict(row) for row in self.db.cursor.execute(
            "SELECT * FROM expiry_option_observations WHERE underlying=? ORDER BY observed_at DESC LIMIT ?",
            (underlying, limit)).fetchall()]

    def historical_events(self, underlying, limit=2000):
        return [dict(row) for row in self.db.cursor.execute(
            "SELECT * FROM expiry_spike_events WHERE underlying=? ORDER BY started_at DESC LIMIT ?",
            (underlying, limit)).fetchall()]
