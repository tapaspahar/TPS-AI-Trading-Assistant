"""Angel One SmartAPI session helper.

Credentials are supplied in memory by the UI and are never persisted here.
Market-data methods are read-only.  Order methods are deliberately small and
are called only by the separately armed safeguarded execution service.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from threading import Lock
from time import monotonic, sleep


class AngelOneClient:
    provider_name = "Angel One"
    # Historical candle requests have a stricter SmartAPI limit than quotes.
    # Serialising them also avoids several UI pages exhausting the limit together.
    CANDLE_REQUEST_INTERVAL_SECONDS = 3.5
    CANDLE_CACHE_SECONDS = 30
    CANDLE_RETRY_DELAYS_SECONDS = (15, 30)

    @staticmethod
    def _suppress_sensitive_smartapi_logs() -> None:
        """SmartAPI logs full request headers on failures, including auth tokens."""
        try:
            import logzero
            logzero.loglevel(logging.CRITICAL, update_custom_handlers=True)
        except ImportError:
            pass

    def __init__(self, api_key: str, client_code: str, pin: str, totp_secret: str):
        self.api_key = api_key.strip()
        self.client_code = client_code.strip().upper()
        self.pin = pin
        self.totp_secret = totp_secret.replace(" ", "")
        self.session = None
        self._candle_lock = Lock()
        self._last_candle_request_at = 0.0
        self._candle_cache = {}

    def connect(self) -> dict:
        if not all((self.api_key, self.client_code, self.pin, self.totp_secret)):
            raise ValueError("Enter API Key, Client Code, MPIN and TOTP secret.")
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as error:
            raise RuntimeError("Angel One packages are not installed. Run the project requirements install.") from error
        client = SmartConnect(api_key=self.api_key)
        self._suppress_sensitive_smartapi_logs()
        try:
            response = client.generateSession(self.client_code, self.pin, pyotp.TOTP(self.totp_secret).now())
        except Exception as error:
            message = str(error).lower()
            if "access rate" in message or "rate limit" in message:
                raise RuntimeError(
                    "Angel One has temporarily limited login requests. Wait 60 seconds, then open the app once "
                    "or use Connect Live Data once. Do not repeatedly restart or reconnect."
                ) from error
            raise RuntimeError("Angel One login is temporarily unavailable. Check internet, then try once after a minute.") from error
        if not response.get("status"):
            message = response.get("message", "Angel One login failed.")
            if "access rate" in str(message).lower() or "rate limit" in str(message).lower():
                raise RuntimeError("Angel One has temporarily limited login requests. Wait 60 seconds before trying once again.")
            raise RuntimeError(message)
        self.session = client
        self.auth_token = response["data"]["jwtToken"]
        try:
            self.feed_token = client.getfeedToken()
        except Exception as error:
            self.session = None
            raise RuntimeError("Angel One login succeeded but the live-feed token is temporarily unavailable. Try once after a minute.") from error
        return {"connected": True, "message": "Connected for read-only market data."}

    def get_recent_candles(self, exchange: str, token: str, interval: str = "FIVE_MINUTE", days: int = 5):
        """Fetch recent OHLCV data only; this method never submits an order."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading market candles.")
        cache_key = (exchange, str(token), interval, int(days))
        cached = self._candle_cache.get(cache_key)
        if cached and monotonic() - cached[0] < self.CANDLE_CACHE_SECONDS:
            return cached[1]

        # Keep every candle call in one queue. This includes multi-timeframe
        # analysis and live setup capture, both of which may run in UI threads.
        with self._candle_lock:
            cached = self._candle_cache.get(cache_key)
            if cached and monotonic() - cached[0] < self.CANDLE_CACHE_SECONDS:
                return cached[1]

            response = None
            for attempt in range(3):
                wait_seconds = self.CANDLE_REQUEST_INTERVAL_SECONDS - (monotonic() - self._last_candle_request_at)
                if wait_seconds > 0:
                    sleep(wait_seconds)
                end = datetime.now()
                start = end - timedelta(days=days)
                self._last_candle_request_at = monotonic()
                try:
                    response = self.session.getCandleData({
                        "exchange": exchange,
                        "symboltoken": str(token),
                        "interval": interval,
                        "fromdate": start.strftime("%Y-%m-%d %H:%M"),
                        "todate": end.strftime("%Y-%m-%d %H:%M"),
                    })
                except Exception as error:
                    message = str(error)
                    lowered = message.lower()
                    retryable = any(marker in lowered for marker in ("access rate", "rate limit", "timeout", "connection", "ab1004", "try after sometime"))
                    if retryable and attempt < 2:
                        sleep(self.CANDLE_RETRY_DELAYS_SECONDS[attempt])
                        continue
                    if retryable:
                        raise RuntimeError("Angel One candle service is temporarily busy after 3 retries.") from error
                    raise RuntimeError(f"Angel One candle request failed: {message}") from error

                if response.get("status"):
                    break
                message = str(response.get("message", "Angel One candle data is unavailable."))
                error_code = str(response.get("errorcode", ""))
                lowered = message.lower()
                retryable = error_code.upper() == "AB1004" or any(marker in lowered for marker in ("rate limit", "access rate", "try after sometime", "temporarily"))
                if retryable and attempt < 2:
                    sleep(self.CANDLE_RETRY_DELAYS_SECONDS[attempt])
                    continue
                if retryable:
                    raise RuntimeError(f"Angel One candle service is temporarily busy after 3 retries ({error_code or 'transient error'}).")
                raise RuntimeError(message)

            if not response.get("status"):
                raise RuntimeError(response.get("message", "Angel One candle data is unavailable."))
            candles = []
            for row in response.get("data") or []:
                if len(row) < 5:
                    continue
                candles.append({
                    "time": row[0], "open": float(row[1]), "high": float(row[2]),
                    "low": float(row[3]), "close": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0,
                })
            if not candles:
                raise RuntimeError("No recent candles were returned for this symbol.")
            self._candle_cache[cache_key] = (monotonic(), candles)
            return candles

    def get_option_quote(self, exchange: str, token: str):
        """Fetch read-only FULL quote data for one selected option contract."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading option data.")
        self._suppress_sensitive_smartapi_logs()
        try:
            response = self.session.getMarketData("FULL", {exchange: [str(token)]})
        except Exception as error:
            raise RuntimeError("Angel One quote request timed out or is temporarily unavailable. TPS will retry on the next refresh.") from error
        if not response.get("status"):
            raise RuntimeError(response.get("message", "Angel One option quote is unavailable."))
        fetched = (response.get("data") or {}).get("fetched") or []
        if not fetched:
            raise RuntimeError("No live quote was returned for this option contract.")
        return fetched[0]

    def get_option_chain_quotes(self, exchange: str, tokens):
        """Fetch read-only FULL quotes for the selected option-chain window (max 50 tokens)."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading option-chain data.")
        self._suppress_sensitive_smartapi_logs()
        tokens = [str(token) for token in tokens]
        if not tokens:
            return []
        if len(tokens) > 50:
            raise ValueError("Option-chain request exceeds Angel One's 50-token quote limit.")
        try:
            response = self.session.getMarketData("FULL", {exchange: tokens})
        except Exception as error:
            raise RuntimeError("Angel One option-chain request timed out or is temporarily unavailable. TPS will retry on the next refresh.") from error
        if not response.get("status"):
            raise RuntimeError(response.get("message", "Angel One option-chain data is unavailable."))
        return (response.get("data") or {}).get("fetched") or []

    def get_market_quotes(self, exchange_tokens):
        """Fetch read-only FULL quotes for a small mixed-exchange market overview."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading market overview data.")
        self._suppress_sensitive_smartapi_logs()
        try:
            response = self.session.getMarketData("FULL", exchange_tokens)
        except Exception as error:
            raise RuntimeError("Angel One market-data request timed out or is temporarily unavailable. TPS will retry on the next refresh.") from error
        if not response.get("status"):
            raise RuntimeError(response.get("message", "Angel One market overview is unavailable."))
        return (response.get("data") or {}).get("fetched") or []

    def get_put_call_ratios(self):
        """Return Angel One's market-level PCR records when the endpoint is enabled."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading PCR data.")
        self._suppress_sensitive_smartapi_logs()
        try:
            response = self.session.putCallRatio()
        except Exception as error:
            raise RuntimeError("Angel One PCR request timed out or is temporarily unavailable. TPS will retry on the next refresh.") from error
        if not response.get("status"):
            raise RuntimeError(response.get("message", "Angel One PCR data is unavailable."))
        return response.get("data") or []

    def place_limit_order(self, order: dict) -> dict:
        """Submit one validated LIMIT order; never infer that acceptance means fill."""
        if not self.session:
            raise RuntimeError("Connect Angel One before submitting an order.")
        payload = {
            "variety": "NORMAL", "tradingsymbol": str(order["trading_symbol"]),
            "symboltoken": str(order["symbol_token"]), "transactiontype": str(order["side"]).upper(),
            "exchange": str(order["exchange"]).upper(), "ordertype": "LIMIT",
            "producttype": str(order.get("product_type", "INTRADAY")).upper(),
            "duration": "DAY", "price": str(order["limit_price"]),
            "squareoff": "0", "stoploss": "0", "quantity": str(order["quantity"]),
        }
        self._suppress_sensitive_smartapi_logs()
        try:
            if hasattr(self.session, "placeOrderFullResponse"):
                response = self.session.placeOrderFullResponse(payload)
            else:
                order_id = self.session.placeOrder(payload)
                response = {"status": bool(order_id), "data": {"orderid": order_id}}
        except Exception as error:
            raise RuntimeError("Angel One rejected or could not accept the order request.") from error
        if not response or not response.get("status"):
            raise RuntimeError(str((response or {}).get("message", "Angel One order submission failed.")))
        data = response.get("data") or {}
        return {"order_id": str(data.get("orderid") or data.get("orderId") or ""),
                "unique_order_id": str(data.get("uniqueorderid") or ""), "raw": response}

    def get_order_book(self) -> list[dict]:
        if not self.session:
            raise RuntimeError("Connect Angel One before checking order status.")
        response = self.session.orderBook()
        if not response or not response.get("status"):
            raise RuntimeError(str((response or {}).get("message", "Order book unavailable.")))
        return response.get("data") or []

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> dict:
        if not self.session:
            raise RuntimeError("Connect Angel One before cancelling an order.")
        response = self.session.cancelOrder(str(order_id), str(variety))
        if isinstance(response, dict) and not response.get("status", True):
            raise RuntimeError(str(response.get("message", "Order cancellation failed.")))
        return response if isinstance(response, dict) else {"status": True, "data": response}
