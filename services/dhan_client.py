"""Read-only DhanHQ v2 adapter with automatic daily token generation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import requests

from services.dhan_instrument_mapper import DhanInstrumentMapper


class DhanClient:
    provider_name = "Dhan"
    API_ROOT = "https://api.dhan.co/v2"
    AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"
    CANDLE_CACHE_SECONDS = 30

    def __init__(self, client_id, pin, totp_secret, mapper=None, http=None):
        self.client_id = str(client_id).strip()
        self.pin = str(pin).strip()
        self.totp_secret = str(totp_secret).replace(" ", "").strip()
        self.mapper = mapper or DhanInstrumentMapper()
        self.http = http or requests.Session()
        self.session = None
        self.access_token = None
        self.auth_token = None
        self.token_expiry = None
        self.token_generated_at = 0.0
        self.profile = {}
        self._token_lock = Lock()
        self._quote_lock = Lock()
        self._last_quote_at = 0.0
        self._candle_cache = {}

    def connect(self):
        self._generate_token()
        profile = self._request("GET", "/profile")
        self.profile = profile
        self.session = self.http
        name = profile.get("dhanClientName") or profile.get("clientName") or "Dhan account"
        data_plan = str(profile.get("dataPlan") or "").strip().lower()
        if data_plan in {"inactive", "deactive", "disabled", "false"}:
            message = (
                f"{name} login connected, but the Dhan Data API plan is inactive. "
                "Activate Data APIs in DhanHQ Trading APIs before TPS can fetch live quotes and candles."
            )
        else:
            message = f"{name} connected for read-only market data with automatic daily renewal."
        return {"connected": True, "message": message, "data_plan": profile.get("dataPlan")}

    def _generate_token(self):
        if not all((self.client_id, self.pin, self.totp_secret)):
            raise ValueError("Enter Client ID, Dhan PIN and TOTP Secret.")
        try:
            import pyotp
            totp = pyotp.TOTP(self.totp_secret).now()
        except Exception as error:
            raise RuntimeError("Dhan TOTP Secret is invalid. Copy the setup secret, not the current 6-digit code.") from error
        try:
            response = self.http.post(
                self.AUTH_URL,
                params={"dhanClientId": self.client_id, "pin": self.pin, "totp": totp},
                timeout=20,
            )
            data = self._response_json(response, "Dhan login")
        except requests.RequestException as error:
            raise RuntimeError("Dhan login service is unavailable. Check internet and try again.") from error
        token = data.get("accessToken")
        if not token:
            raise RuntimeError(
                data.get("errorMessage") or data.get("message")
                or "Dhan did not issue an access token. Check Client ID, PIN and TOTP setup."
            )
        self.access_token = self.auth_token = str(token)
        self.token_generated_at = monotonic()
        expiry = str(data.get("expiryTime") or "").replace("Z", "+00:00")
        try:
            self.token_expiry = datetime.fromisoformat(expiry)
            if self.token_expiry.tzinfo is None:
                self.token_expiry = self.token_expiry.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        except ValueError:
            self.token_expiry = datetime.now(timezone.utc) + timedelta(hours=23)

    def _ensure_token(self):
        now = datetime.now(timezone.utc)
        expiry = self.token_expiry.astimezone(timezone.utc) if self.token_expiry else None
        if self.access_token and expiry and now < expiry - timedelta(minutes=5):
            return
        with self._token_lock:
            now = datetime.now(timezone.utc)
            expiry = self.token_expiry.astimezone(timezone.utc) if self.token_expiry else None
            if not self.access_token or not expiry or now >= expiry - timedelta(minutes=5):
                self._generate_token()

    @staticmethod
    def _response_json(response, operation):
        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(f"{operation} returned an unreadable response.") from error
        if not response.ok or (isinstance(data, dict) and str(data.get("status", "")).lower() in {"failure", "failed"}):
            raise RuntimeError(data.get("errorMessage") or data.get("message") or f"{operation} failed (HTTP {response.status_code}).")
        return data

    def _request(self, method, path, *, json=None):
        self._ensure_token()
        data_plan = str((self.profile or {}).get("dataPlan") or "").strip().lower()
        if path != "/profile" and data_plan in {"inactive", "deactive", "disabled", "false"}:
            raise RuntimeError(
                "Dhan Data API plan is inactive. Open DhanHQ Trading APIs and activate Data APIs, "
                "then reconnect TPS."
            )
        headers = {
            "Accept": "application/json", "Content-Type": "application/json",
            "access-token": self.access_token, "client-id": self.client_id,
        }
        try:
            response = self.http.request(method, self.API_ROOT + path, headers=headers, json=json, timeout=30)
        except requests.RequestException as error:
            raise RuntimeError("Dhan market-data service is temporarily unavailable.") from error
        # Dhan allows automatic TOTP token generation only once every two
        # minutes.  A newly generated token that is rejected by a data
        # endpoint usually indicates a data-plan/permission problem, not an
        # expired token.  Preserve the original response instead of masking it
        # with a second-token rate-limit error.
        token_old_enough = monotonic() - self.token_generated_at >= 120
        if response.status_code == 401 and token_old_enough:
            with self._token_lock:
                self._generate_token()
            headers["access-token"] = self.access_token
            response = self.http.request(method, self.API_ROOT + path, headers=headers, json=json, timeout=30)
        return self._response_json(response, "Dhan API")

    @staticmethod
    def _interval(interval):
        return {
            "ONE_MINUTE": "1", "FIVE_MINUTE": "5", "FIFTEEN_MINUTE": "15",
            "THIRTY_MINUTE": "15", "ONE_HOUR": "60",
        }.get(interval, "5")

    @staticmethod
    def _candles(data):
        keys = ("timestamp", "open", "high", "low", "close", "volume")
        size = min((len(data.get(key) or []) for key in keys), default=0)
        result = []
        for index in range(size):
            stamp = datetime.fromtimestamp(float(data["timestamp"][index]), tz=timezone.utc).astimezone().isoformat()
            result.append({
                "time": stamp, "open": float(data["open"][index]), "high": float(data["high"][index]),
                "low": float(data["low"][index]), "close": float(data["close"][index]),
                "volume": float(data["volume"][index] or 0),
            })
        return result

    @staticmethod
    def _aggregate_30(candles):
        output = []
        for start in range(0, len(candles), 2):
            pair = candles[start:start + 2]
            if len(pair) < 2:
                continue
            output.append({
                "time": pair[0]["time"], "open": pair[0]["open"],
                "high": max(x["high"] for x in pair), "low": min(x["low"] for x in pair),
                "close": pair[-1]["close"], "volume": sum(x["volume"] for x in pair),
            })
        return output

    def get_recent_candles(self, exchange, token, interval="FIVE_MINUTE", days=5):
        instrument = self.mapper.resolve(exchange, token)
        cache_key = (exchange, str(token), interval, int(days))
        cached = self._candle_cache.get(cache_key)
        if cached and monotonic() - cached[0] < self.CANDLE_CACHE_SECONDS:
            return cached[1]
        end, start = datetime.now(), datetime.now() - timedelta(days=int(days))
        daily = interval in {"ONE_DAY", "DAY"}
        body = {
            "securityId": instrument.security_id, "exchangeSegment": instrument.exchange_segment,
            "instrument": instrument.instrument, "oi": instrument.instrument.startswith(("FUT", "OPT")),
            "fromDate": start.strftime("%Y-%m-%d" if daily else "%Y-%m-%d %H:%M:%S"),
            "toDate": (end + timedelta(days=1)).strftime("%Y-%m-%d" if daily else "%Y-%m-%d %H:%M:%S"),
        }
        if not daily:
            body["interval"] = self._interval(interval)
        data = self._request("POST", "/charts/historical" if daily else "/charts/intraday", json=body)
        candles = self._candles(data)
        if interval == "THIRTY_MINUTE":
            candles = self._aggregate_30(candles)
        if not candles:
            raise RuntimeError(f"Dhan returned no recent candles for {instrument.symbol}.")
        self._candle_cache[cache_key] = (monotonic(), candles)
        return candles

    @staticmethod
    def _quote_row(original_token, item):
        ohlc, depth = item.get("ohlc") or {}, item.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        previous = float(ohlc.get("close") or 0)
        ltp = float(item.get("last_price") or 0)
        return {
            "token": str(original_token), "symbolToken": str(original_token), "ltp": ltp,
            "open": float(ohlc.get("open") or 0), "high": float(ohlc.get("high") or 0),
            "low": float(ohlc.get("low") or 0), "close": previous,
            "tradeVolume": float(item.get("volume") or 0), "volume": float(item.get("volume") or 0),
            "opnInterest": float(item.get("oi") or 0), "openInterest": float(item.get("oi") or 0),
            "netChange": float(item.get("net_change") or 0),
            "percentChange": ((ltp - previous) / previous * 100) if previous else 0,
            "depth": depth,
            "bestBidPrice": float((buys[0] if buys else {}).get("price") or 0),
            "bestAskPrice": float((sells[0] if sells else {}).get("price") or 0),
        }

    def _quotes(self, exchange_tokens):
        translated, request = {}, {}
        for exchange, tokens in exchange_tokens.items():
            for token in tokens:
                instrument = self.mapper.resolve(exchange, token)
                request.setdefault(instrument.exchange_segment, []).append(int(instrument.security_id))
                translated[(instrument.exchange_segment, instrument.security_id)] = str(token)
        with self._quote_lock:
            wait = 1.05 - (monotonic() - self._last_quote_at)
            if wait > 0:
                sleep(wait)
            data = self._request("POST", "/marketfeed/quote", json=request)
            self._last_quote_at = monotonic()
        rows = []
        for segment, values in (data.get("data") or {}).items():
            for security_id, item in (values or {}).items():
                original = translated.get((segment, str(security_id)))
                if original is not None:
                    rows.append(self._quote_row(original, item or {}))
        return rows

    def get_option_quote(self, exchange, token):
        rows = self._quotes({exchange: [str(token)]})
        if not rows:
            raise RuntimeError("Dhan returned no quote for this instrument.")
        return rows[0]

    def get_option_chain_quotes(self, exchange, tokens):
        return self._quotes({exchange: [str(token) for token in tokens]})

    def get_market_quotes(self, exchange_tokens):
        return self._quotes(exchange_tokens)

    def get_put_call_ratios(self):
        raise RuntimeError(
            "Dhan does not provide a separate market-level PCR endpoint; "
            "TPS calculates focused-expiry PCR from live OI."
        )
