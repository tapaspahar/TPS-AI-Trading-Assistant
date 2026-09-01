from core.database_manager import Database
from services.order_intelligence import OrderIntelligenceService, analyze_order


class Client:
    def get_order_book(self):
        return [{"orderid": "A1", "tradingsymbol": "NIFTYCE", "exchange": "NFO", "symboltoken": "1",
                 "transactiontype": "BUY", "averageprice": 100, "quantity": 65, "status": "complete"}]

    def get_option_quote(self, exchange, token): return {"ltp": 112}
    def get_recent_candles(self, exchange, token, interval, days):
        return [{"high": 120, "low": 95, "close": 112}]


def test_live_order_analysis_calculates_mfe_mae_and_state():
    result = analyze_order(
        {"orderid": "A1", "tradingsymbol": "NIFTYCE", "transactiontype": "BUY", "averageprice": 100, "status": "complete"},
        {"ltp": 112}, [{"high": 120, "low": 95}],
    )
    assert result["unrealized_points"] == 12
    assert result["mfe_points"] == 20
    assert result["mae_points"] == 5
    assert result["analysis_state"] == "HOLD REVIEW"


def test_missing_live_quote_stays_data_gap():
    result = analyze_order({"orderid": "A1", "averageprice": 100, "status": "complete"})
    assert result["analysis_state"] == "DATA GAP"
    assert not result["source_complete"]


def test_scan_persists_read_only_order_snapshot(tmp_path):
    db = Database(tmp_path / "orders.db")
    result = OrderIntelligenceService(Client(), db).scan()
    assert len(result) == 1
    rows = db.get_order_intelligence_snapshots()
    assert len(rows) == 1
    assert rows[0]["broker_order_id"] == "A1"
    assert rows[0]["analysis_state"] == "HOLD REVIEW"
