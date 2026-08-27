from core.database_manager import Database
from services.expiry_observation_store import ExpiryObservationStore


def test_expiry_event_schema_and_paired_prices_are_upgrade_safe(tmp_path):
    database = Database(tmp_path / "expiry.db")
    store = ExpiryObservationStore(database)
    columns = {row["name"] for row in database.cursor.execute("PRAGMA table_info(expiry_spike_events)")}
    assert {
        "spike_start_premium", "spike_event_premium", "spike_latest_premium",
        "opposite_contract_symbol", "opposite_option_type", "opposite_start_premium",
        "opposite_event_premium", "opposite_latest_premium", "opposite_change_pct",
        "paired_last_updated_at",
    } <= columns
    row = {
        "event_key": "2026-08-27|NIFTY24500CE|151800", "trade_date": "2026-08-27",
        "started_at": "2026-08-27T15:18:00+05:30", "last_seen_at": "2026-08-27T15:20:00+05:30",
        "underlying": "NIFTY", "contract_symbol": "NIFTY24500CE", "strike": 24500,
        "option_type": "CE", "moneyness": "ATM", "premium": 60, "peak_change_pct": 200,
        "spot": 24510, "duration_seconds": 120, "cas_context": "INDEX OPTIONS CONTINUOUS",
        "source_completeness": "COMPLETE", "event_text": "paired event",
        "spike_start_premium": 20, "spike_event_premium": 60, "spike_latest_premium": 55,
        "opposite_contract_symbol": "NIFTY24500PE", "opposite_option_type": "PE",
        "opposite_start_premium": 40, "opposite_event_premium": 22, "opposite_latest_premium": 18,
        "opposite_change_pct": -55, "paired_last_updated_at": "2026-08-27T15:20:00+05:30",
    }
    store.save_event(row)
    saved = store.events()[0]
    assert saved["spike_start_premium"] == 20
    assert saved["opposite_event_premium"] == 22
    assert saved["opposite_latest_premium"] == 18
    database.connection.close()
