import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.database_manager import Database
from engine.index_candle_analysis_engine import analyze_index_candle, combine_index_candles


def candles(direction="bull"):
    rows = []
    for i in range(12):
        opening = 100 + i
        close = opening + (4 if direction == "bull" and i == 11 else -4 if direction == "bear" and i == 11 else 1)
        rows.append({"time": f"2026-08-29T10:{i:02d}:00", "open": opening, "high": max(opening, close)+.5,
                     "low": min(opening, close)-.5, "close": close, "volume": 100 if i < 11 else 220})
    return rows


def test_index_candle_price_oi_alignment():
    result = analyze_index_candle("NIFTY", candles(), {"direction": "BULLISH FLOW", "quality": 80, "call_coi": 10, "put_coi": 30})
    assert result["state"] == "PRICE + OI ALIGNED"
    assert result["aggression"] == "BUYERS AGGRESSIVE"
    assert "Future volume" not in result["explanation"]


def test_cas_is_explicit_not_normal_candle_claim():
    result = analyze_index_candle("SENSEX", candles("bear"), {"direction": "BEARISH FLOW", "quality": 90}, cas_active=True)
    assert result["state"] == "CAS / SETTLEMENT REPRICING"
    assert "stale" in result["explanation"]


def test_cross_index_breadth():
    result = combine_index_candles([{"symbol": s, "direction": "BEARISH"} for s in ("NIFTY", "BANKNIFTY", "SENSEX")])
    assert result["state"] == "BROAD BEARISH"
    assert result["coverage"] == "3/3"


def test_index_analysis_database_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    row = analyze_index_candle("NIFTY", candles(), {"direction": "BALANCED FLOW", "quality": 70})
    row.update({"trade_date": "29-08-2026", "candle_time": "2026-08-29T10:10", "analyzed_at": "2026-08-29T10:15:01",
                "symbol": "NIFTY", "details_json": json.dumps({"source": "test"})})
    assert db.save_index_candle_analysis(row)
    assert not db.save_index_candle_analysis(row)
    assert len(db.get_index_candle_analyses("29-08-2026")) == 1
    db.save_index_daily_analysis({"trade_date": "29-08-2026", "generated_at": "2026-08-29T15:40:00", "market_state": "MIXED",
                                  "source_completeness": 75, "summary_text": "saved", "details_json": "{}"})
    assert db.get_index_daily_analysis("29-08-2026")["summary_text"] == "saved"
    db.close()


def test_index_page_has_content_columns_and_both_scrollbars(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QHeaderView
    from ui.pages.index_market_analysis_page import IndexMarketAnalysisPage
    app = QApplication.instance() or QApplication([])
    page = IndexMarketAnalysisPage()
    assert page.table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert page.table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert page.table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeToContents
    assert page.table.horizontalHeader().sectionResizeMode(9) == QHeaderView.Interactive
    assert page.table.columnWidth(9) >= 640
    page.close()
