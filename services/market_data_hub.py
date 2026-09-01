"""Process-wide, timestamped market-data cache and health telemetry.

Every analysis page should consume the same short-lived broker snapshot instead
of independently downloading an equivalent candle/quote/chain payload.  The hub
does not extend the useful life of market data: callers choose a small TTL and
can force a fresh read for final execution/capture verification.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from time import monotonic


class MarketDataHub:
    _lock = Lock()
    _cache = {}
    _metrics = {
        "requests": 0, "hits": 0, "misses": 0, "failures": 0,
        "last_success_at": None, "last_failure_at": None,
        "last_error": "", "last_source_timestamp": None,
    }

    @classmethod
    def _provider(cls, client):
        return str(getattr(client, "provider_name", client.__class__.__name__))

    @classmethod
    def _read(cls, key, loader, ttl_seconds, *, force=False, source_timestamp=None):
        now = monotonic()
        with cls._lock:
            cls._metrics["requests"] += 1
            cached = cls._cache.get(key)
            if not force and cached and now - cached["saved"] <= max(0.0, float(ttl_seconds)):
                cls._metrics["hits"] += 1
                return deepcopy(cached["value"])
            cls._metrics["misses"] += 1
        try:
            value = loader()
        except Exception as error:
            with cls._lock:
                cls._metrics["failures"] += 1
                cls._metrics["last_failure_at"] = datetime.now().isoformat(timespec="seconds")
                cls._metrics["last_error"] = f"{type(error).__name__}: {error}"
            raise
        stamp = source_timestamp(value) if source_timestamp else None
        with cls._lock:
            cls._cache[key] = {"saved": monotonic(), "value": deepcopy(value)}
            cls._metrics["last_success_at"] = datetime.now().isoformat(timespec="seconds")
            cls._metrics["last_source_timestamp"] = stamp or cls._metrics["last_source_timestamp"]
            cls._metrics["last_error"] = ""
        return deepcopy(value)

    @classmethod
    def candles(cls, client, exchange, token, interval="FIVE_MINUTE", days=5, *, ttl_seconds=4, force=False):
        key = (cls._provider(client), "candles", str(exchange), str(token), str(interval), int(days))
        return cls._read(
            key, lambda: list(client.get_recent_candles(exchange, token, interval, days)), ttl_seconds,
            force=force,
            source_timestamp=lambda rows: str((rows or [{}])[-1].get("time") or (rows or [{}])[-1].get("timestamp") or ""),
        )

    @classmethod
    def quote(cls, client, exchange, token, *, ttl_seconds=1.5, force=False):
        key = (cls._provider(client), "quote", str(exchange), str(token))
        return cls._read(key, lambda: dict(client.get_option_quote(exchange, token)), ttl_seconds, force=force)

    @classmethod
    def option_chain(cls, client, exchange, tokens, *, ttl_seconds=2, force=False):
        normalized = tuple(str(token) for token in tokens)
        key = (cls._provider(client), "chain", str(exchange), normalized)
        return cls._read(
            key, lambda: list(client.get_option_chain_quotes(exchange, list(tokens))), ttl_seconds, force=force,
        )

    @classmethod
    def invalidate(cls, provider=None):
        with cls._lock:
            if provider is None:
                cls._cache.clear()
            else:
                provider = str(provider)
                cls._cache = {key: value for key, value in cls._cache.items() if key[0] != provider}

    @classmethod
    def health(cls):
        with cls._lock:
            result = dict(cls._metrics)
            result["cached_snapshots"] = len(cls._cache)
        requests = int(result["requests"])
        result["hit_rate"] = round(100.0 * int(result["hits"]) / requests, 1) if requests else 0.0
        result["state"] = "DEGRADED" if result["last_error"] else "READY" if result["last_success_at"] else "WAITING"
        return result
