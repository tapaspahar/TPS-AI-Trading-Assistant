"""Official Paytm Money Open API adapter for read-only TPS market data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic, sleep
from urllib.parse import quote_plus

import requests

from services.paytm_money_instrument_mapper import PaytmMoneyInstrumentMapper


class PaytmMoneyClient:
    provider_name = "Paytm Money"
    API_ROOT = "https://developer.paytmmoney.com"
    LOGIN_ROOT = "https://login.paytmmoney.com/merchant-login"
    CANDLE_CACHE_SECONDS = 30

    def __init__(self, api_key, api_secret, request_token="", access_token="", read_access_token="", public_access_token="", mapper=None, http=None):
        self.api_key = str(api_key).strip()
        self.api_secret = str(api_secret).strip()
        self.request_token = str(request_token).strip()
        self.access_token = str(access_token).strip()
        self.read_access_token = str(read_access_token).strip()
        self.public_access_token = str(public_access_token).strip()
        self.mapper = mapper or PaytmMoneyInstrumentMapper()
        self.http = http or requests.Session()
        self.session = None
        self.auth_token = self.read_access_token or self.access_token
        self.profile = {}
        self._quote_lock = Lock()
        self._last_quote_at = 0.0
        self._candle_cache = {}

    def login_url(self, state="tps-ai-trading-assistant"):
        if not self.api_key:
            raise ValueError("Enter Paytm Money API Key first.")
        return f"{self.LOGIN_ROOT}?apiKey={quote_plus(self.api_key)}&state={quote_plus(state)}"

    def export_credentials(self):
        return {
            "api_key": self.api_key, "api_secret": self.api_secret,
            "request_token": "", "access_token": self.access_token,
            "read_access_token": self.read_access_token,
            "public_access_token": self.public_access_token,
        }

    @staticmethod
    def _response_json(response, operation):
        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(f"{operation} returned an unreadable response.") from error
        failed = isinstance(data, dict) and (
            str(data.get("status", "")).lower() in {"failure", "failed", "error"}
            or data.get("success") is False
        )
        if not response.ok or failed:
            message = data.get("message") or data.get("errorMessage") or data.get("error") if isinstance(data, dict) else ""
            raise RuntimeError(message or f"{operation} failed (HTTP {response.status_code}).")
        return data

    def _generate_session(self):
        if not self.request_token:
            raise ValueError(
                "Open Paytm Login, authorize TPS, then paste the request_token from the redirect URL."
            )
        body = {"api_key": self.api_key, "api_secret_key": self.api_secret, "request_token": self.request_token}
        try:
            response = self.http.post(self.API_ROOT + "/accounts/v2/gettoken", json=body, timeout=25)
        except requests.RequestException as error:
            raise RuntimeError("Paytm Money login service is unavailable. Check internet and try again.") from error
        data = self._response_json(response, "Paytm Money login")
        self.access_token = str(data.get("access_token") or "")
        self.read_access_token = str(data.get("read_access_token") or "")
        self.public_access_token = str(data.get("public_access_token") or "")
        self.auth_token = self.read_access_token or self.access_token
        if not self.auth_token:
            raise RuntimeError("Paytm Money did not return a market-data token. Re-authorize the application.")

    def connect(self):
        if not self.api_key or not self.api_secret:
            raise ValueError("Enter Paytm Money API Key and API Secret.")
        if not (self.read_access_token or self.access_token):
            self._generate_session()
        self.auth_token = self.read_access_token or self.access_token
        try:
            self.profile = self._request("GET", "/accounts/v1/user/details")
        except RuntimeError as error:
            if self.request_token:
                self._generate_session()
                self.profile = self._request("GET", "/accounts/v1/user/details")
            else:
                raise RuntimeError(f"Saved Paytm Money token is no longer valid. Re-authorize TPS. {error}") from error
        self.session = self.http
        profile = self.profile.get("data") if isinstance(self.profile.get("data"), dict) else self.profile
        name = profile.get("name") or profile.get("user_name") or profile.get("client_name") or "Paytm Money account"
        return {"connected": True, "message": f"{name} connected for read-only Paytm Money market data."}

    def _request(self, method, path, *, params=None, json=None):
        headers = {
            "Accept": "application/json", "Content-Type": "application/json",
            "x-jwt-token": self.read_access_token or self.access_token,
            "openapi-client-src": "tps-read-only",
        }
        try:
            response = self.http.request(method, self.API_ROOT + path, headers=headers, params=params, json=json, timeout=30)
        except requests.RequestException as error:
            raise RuntimeError("Paytm Money market-data service is temporarily unavailable.") from error
        return self._response_json(response, "Paytm Money API")

    @staticmethod
    def _number(item, *names):
        for name in names:
            value = item.get(name)
            if value not in (None, ""):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        return 0.0

    @classmethod
    def _quote_row(cls, original_token, item):
        ohlc = item.get("ohlc") or item.get("OHLC") or {}
        ltp = cls._number(item, "last_price", "ltp", "last_traded_price", "lastPrice")
        previous = cls._number(ohlc, "close", "previous_close") or cls._number(item, "close", "previous_close")
        depth = item.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        return {
            "token": str(original_token), "symbolToken": str(original_token), "ltp": ltp,
            "open": cls._number(ohlc, "open") or cls._number(item, "open"),
            "high": cls._number(ohlc, "high") or cls._number(item, "high"),
            "low": cls._number(ohlc, "low") or cls._number(item, "low"), "close": previous,
            "tradeVolume": cls._number(item, "volume", "trade_volume", "total_volume"),
            "volume": cls._number(item, "volume", "trade_volume", "total_volume"),
            "opnInterest": cls._number(item, "oi", "open_interest"),
            "openInterest": cls._number(item, "oi", "open_interest"),
            "netChange": cls._number(item, "net_change", "change"),
            "percentChange": ((ltp - previous) / previous * 100) if previous else cls._number(item, "percent_change", "change_percent"),
            "depth": depth,
            "bestBidPrice": cls._number(buys[0], "price") if buys else cls._number(item, "best_bid_price"),
            "bestAskPrice": cls._number(sells[0], "price") if sells else cls._number(item, "best_ask_price"),
        }

    def _quotes(self, exchange_tokens):
        translated, preferences = {}, []
        for exchange, tokens in exchange_tokens.items():
            for token in tokens:
                instrument = self.mapper.resolve(exchange, token)
                preferences.append(f"{instrument.exchange}:{instrument.security_id}:{instrument.scrip_type}")
                translated[str(instrument.security_id)] = str(token)
        with self._quote_lock:
            wait = 1.05 - (monotonic() - self._last_quote_at)
            if wait > 0:
                sleep(wait)
            data = self._request("GET", "/data/v1/price/live", params={"mode": "FULL", "pref": ",".join(preferences)})
            self._last_quote_at = monotonic()
        values = data.get("data") if isinstance(data, dict) else data
        if isinstance(values, dict):
            values = values.get("data") or values.get("quotes") or list(values.values())
        rows = []
        for item in values or []:
            security_id = str(item.get("security_id") or item.get("securityId") or item.get("scrip_id") or "")
            original = translated.get(security_id)
            if original is not None:
                rows.append(self._quote_row(original, item))
        return rows

    def get_option_quote(self, exchange, token):
        rows = self._quotes({exchange: [str(token)]})
        if not rows:
            raise RuntimeError("Paytm Money returned no quote for this instrument.")
        return rows[0]

    def get_option_chain_quotes(self, exchange, tokens):
        return self._quotes({exchange: [str(token) for token in tokens]})

    def get_market_quotes(self, exchange_tokens):
        return self._quotes(exchange_tokens)

    @staticmethod
    def _parse_time(value):
        if isinstance(value, (int, float)) or str(value).isdigit():
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, timezone.utc).astimezone()
        text = str(value or "").replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            for pattern in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
                try:
                    return datetime.strptime(text, pattern).astimezone()
                except ValueError:
                    continue
        raise ValueError("unreadable candle time")

    @classmethod
    def _candles(cls, data):
        while isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            data = data["data"]
        if isinstance(data, dict) and any(isinstance(data.get(key), list) for key in ("timestamp", "time", "date_time")):
            stamps = data.get("timestamp") or data.get("time") or data.get("date_time") or []
            rows = []
            for index, stamp in enumerate(stamps):
                try:
                    rows.append({key: data.get(key, [])[index] for key in ("open", "high", "low", "close", "volume")} | {"time": stamp})
                except IndexError:
                    continue
            data = rows
        rows = data.get("candles") or data.get("price_data") or data.get("prices") if isinstance(data, dict) else data
        result = []
        for item in rows or []:
            if isinstance(item, dict):
                stamp = item.get("time") or item.get("timestamp") or item.get("date_time") or item.get("Date & Time")
                values = (item.get("open"), item.get("high"), item.get("low"), item.get("close"), item.get("volume", 0))
            else:
                stamp, *values = item
                values = list(values) + [0] * (5 - len(values))
            try:
                when = cls._parse_time(stamp)
                result.append({"time": when.isoformat(), "open": float(values[0]), "high": float(values[1]),
                               "low": float(values[2]), "close": float(values[3]), "volume": float(values[4] or 0)})
            except (TypeError, ValueError, IndexError):
                continue
        return result

    @classmethod
    def _aggregate(cls, candles, minutes):
        if minutes <= 1:
            return candles
        buckets = {}
        for candle in candles:
            when = cls._parse_time(candle["time"])
            bucket = when.replace(minute=(when.minute // minutes) * minutes, second=0, microsecond=0)
            group = buckets.setdefault(bucket, [])
            group.append(candle)
        return [{"time": key.isoformat(), "open": rows[0]["open"], "high": max(x["high"] for x in rows),
                 "low": min(x["low"] for x in rows), "close": rows[-1]["close"],
                 "volume": sum(x["volume"] for x in rows)} for key, rows in sorted(buckets.items())]

    def get_recent_candles(self, exchange, token, interval="FIVE_MINUTE", days=5):
        instrument = self.mapper.resolve(exchange, token)
        cache_key = (exchange, str(token), interval, int(days))
        cached = self._candle_cache.get(cache_key)
        if cached and monotonic() - cached[0] < self.CANDLE_CACHE_SECONDS:
            return cached[1]
        end, start = datetime.now(), datetime.now() - timedelta(days=int(days))
        daily = interval in {"ONE_DAY", "DAY"}
        body = {
            "cont": "false", "exchange": instrument.exchange, "expiry": instrument.expiry or None,
            "fromDate": start.strftime("%Y-%m-%d"), "instType": instrument.instrument_type,
            "interval": "DAY" if daily else "MINUTE", "series": instrument.option_type or None,
            "strike": instrument.strike or None, "symbol": instrument.underlying,
            "toDate": (end + timedelta(days=1)).strftime("%Y-%m-%d"),
        }
        body = {key: value for key, value in body.items() if value not in (None, "")}
        data = self._request("POST", "/data/v1/price-charts/sym", json=body)
        candles = self._candles(data)
        minutes = {"ONE_MINUTE": 1, "FIVE_MINUTE": 5, "FIFTEEN_MINUTE": 15,
                   "THIRTY_MINUTE": 30, "ONE_HOUR": 60}.get(interval, 1)
        if not daily:
            candles = self._aggregate(candles, minutes)
        if not candles:
            raise RuntimeError(f"Paytm Money returned no recent candles for {instrument.symbol}.")
        self._candle_cache[cache_key] = (monotonic(), candles)
        return candles

    def get_put_call_ratios(self):
        raise RuntimeError(
            "Paytm Money does not provide a separate market-level PCR endpoint; "
            "TPS calculates focused-expiry PCR from live OI."
        )
