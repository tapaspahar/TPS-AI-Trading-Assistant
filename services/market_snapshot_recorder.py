"""Timed read-only snapshots for later post-market review."""
from __future__ import annotations

from datetime import datetime

from core.database_manager import Database
from engine.live_setup_capture import INSTRUMENTS, TIMEFRAMES, build_live_capture
from engine.option_chain_engine import analyze_option_chain
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot


class MarketSnapshotRecorder:
    """Save 5m/15m candles plus a focused, current-expiry option-chain context."""

    def __init__(self, client):
        self.client = client

    def capture(self, symbol: str) -> int:
        symbol = symbol.upper()
        if symbol not in INSTRUMENTS:
            raise ValueError("Snapshots currently support NIFTY, BANKNIFTY, and SENSEX.")
        option_context = self._option_context(symbol)
        exchange, token = INSTRUMENTS[symbol]
        captured_at = datetime.now().replace(second=0, microsecond=0)
        database = Database()
        try:
            saved = 0
            for timeframe in ("5m", "15m"):
                interval, days = TIMEFRAMES[timeframe]
                candles = self.client.get_recent_candles(exchange, token, interval, days)
                data = build_live_capture(symbol, timeframe, candles, "Angel One index candle data")
                latest = candles[-1]
                snapshot = {
                    "captured_at": captured_at.isoformat(timespec="minutes"),
                    "trade_date": captured_at.strftime("%d-%m-%Y"),
                    "symbol": symbol, "timeframe": timeframe,
                    "open": float(latest["open"]), "high": float(latest["high"]),
                    "low": float(latest["low"]), "close": float(latest["close"]),
                    **{key: self._number(data.get(key)) for key in ("volume", "volume_ema", "ema_5", "ema_20", "ema_50", "vwap", "supertrend", "rsi_14", "atr_14")},
                    **option_context,
                }
                saved += int(database.save_market_snapshot(snapshot))
            return saved
        finally:
            database.close()

    def _option_context(self, symbol: str) -> dict:
        """A failure to quote option-chain data must not discard the candle snapshot."""
        empty = {"oi_pcr": None, "volume_pcr": None, "put_support": None, "call_resistance": None, "option_contracts": 0}
        try:
            service = OptionContractService()
            quote_config = UNDERLYING_QUOTES[symbol]
            spot_quote = self.client.get_option_quote(quote_config["exchange"], quote_config["token"])
            spot = float(spot_quote.get("ltp", 0) or 0)
            contracts = service.get_contracts(symbol)
            focused = contracts_near_spot(contracts, spot, wings=5)
            expiry = min(contract["expiry"] for contract in focused)
            focused = [contract for contract in focused if contract["expiry"] == expiry]
            quotes = self.client.get_option_chain_quotes(focused[0]["exchange"], [contract["token"] for contract in focused])
            analysis = analyze_option_chain(focused, quotes)
            return {
                "oi_pcr": analysis.get("pcr_oi"), "volume_pcr": analysis.get("pcr_volume"),
                "put_support": analysis.get("put_support"), "call_resistance": analysis.get("call_resistance"),
                "option_contracts": analysis.get("quoted_contracts", 0),
            }
        except (RuntimeError, ValueError, IndexError):
            return empty

    @staticmethod
    def _number(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
