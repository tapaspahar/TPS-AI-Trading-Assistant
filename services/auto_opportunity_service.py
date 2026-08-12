"""Automatic, rate-conscious 5-minute opportunity research service."""

from __future__ import annotations

from engine.auto_opportunity_engine import (
    equity_opportunity, error_opportunity, option_opportunity, stock_option_opportunity,
)
from engine.equity_analysis import analyze_equity
from core.equity_watchlist_store import EquityWatchlistStore
from core.settings_store import SettingsStore
from core.stock_option_watchlist_store import StockOptionWatchlistStore
from services.powerful_engine_service import PowerfulEngineService
from services.stock_derivative_service import StockDerivativeService, _completed
from services.auto_universe_service import AutoUniverseService


class AutoOpportunityService:
    INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")

    def __init__(self, client):
        self.client = client
        self.settings = SettingsStore().load()

    def scan(self, progress=None):
        results = []
        auto_selected = []
        try:
            if progress:
                progress(0, 1, "Auto-selecting liquid F&O stocks")
            auto_selected = AutoUniverseService(self.client).discover()
        except Exception as error:
            results.append(error_opportunity("AUTO DISCOVERY", "F&O UNIVERSE", error))

        stock_rows = _merge_candidates(auto_selected, StockOptionWatchlistStore().load(), 8, "underlying")
        equity_rows = _merge_candidates(auto_selected, EquityWatchlistStore().load(), 8, "symbol")
        tasks = 3 + len(stock_rows) + len(equity_rows)
        done = 0

        def update(label):
            nonlocal done
            done += 1
            if progress:
                progress(done, max(tasks, 1), label)

        powerful = PowerfulEngineService(self.client)
        for symbol in self.INDEX_SYMBOLS:
            try:
                results.append(option_opportunity(powerful.analyze(symbol), self.settings))
            except Exception as error:  # Keep the remaining automatic scan alive if one broker request fails.
                results.append(error_opportunity("INDEX OPTION", symbol, error))
            update(symbol)

        stocks = StockDerivativeService(self.client)
        for equity in stock_rows:
            symbol = equity.get("underlying", "STOCK")
            try:
                analyzed = stocks.analyze_option_setup(equity, self.settings)
                analyzed["selection_reason"] = equity.get("selection_reason")
                analyzed["selection_source"] = equity.get("selection_source", "MANUAL WATCHLIST")
                results.append(stock_option_opportunity(analyzed))
            except Exception as error:  # One unavailable contract must not suppress other opportunities.
                results.append(error_opportunity("STOCK OPTION", symbol, error))
            update(symbol)

        for equity in equity_rows:
            symbol = equity.get("symbol", "EQUITY")
            try:
                candles = _completed(self.client.get_recent_candles(equity["exchange"], equity["token"], "FIVE_MINUTE", 5))
                result = analyze_equity(candles)
                results.append(equity_opportunity(equity, result, candles[-1].get("time")))
            except Exception as error:  # Preserve a complete per-cycle audit across the watchlist.
                results.append(error_opportunity("CASH EQUITY", symbol, error))
            update(symbol)
        return results


def _merge_candidates(automatic, manual, limit, identity):
    """Keep automatic discovery first and fill remaining API-safe slots manually."""
    rows, seen = [], set()
    for item in list(automatic) + list(manual):
        key = str(item.get(identity, "")).upper().strip()
        if not key or key in seen:
            continue
        seen.add(key); rows.append(dict(item))
        if len(rows) >= limit:
            break
    return rows
