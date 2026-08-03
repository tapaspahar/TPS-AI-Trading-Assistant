"""Read-only Angel One SmartAPI session helper.

Credentials are supplied in memory by the UI and are never persisted here.
Order placement is intentionally out of scope.
"""

from __future__ import annotations

from datetime import datetime, timedelta


class AngelOneClient:
    def __init__(self, api_key: str, client_code: str, pin: str, totp_secret: str):
        self.api_key = api_key.strip()
        self.client_code = client_code.strip().upper()
        self.pin = pin
        self.totp_secret = totp_secret.replace(" ", "")
        self.session = None

    def connect(self) -> dict:
        if not all((self.api_key, self.client_code, self.pin, self.totp_secret)):
            raise ValueError("Enter API Key, Client Code, MPIN and TOTP secret.")
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as error:
            raise RuntimeError("Angel One packages are not installed. Run the project requirements install.") from error
        client = SmartConnect(api_key=self.api_key)
        response = client.generateSession(self.client_code, self.pin, pyotp.TOTP(self.totp_secret).now())
        if not response.get("status"):
            raise RuntimeError(response.get("message", "Angel One login failed."))
        self.session = client
        self.auth_token = response["data"]["jwtToken"]
        self.feed_token = client.getfeedToken()
        return {"connected": True, "message": "Connected for read-only market data."}

    def get_recent_candles(self, exchange: str, token: str, interval: str = "FIVE_MINUTE", days: int = 5):
        """Fetch recent OHLCV data only; this method never submits an order."""
        if not self.session:
            raise RuntimeError("Connect Angel One before loading market candles.")
        end = datetime.now()
        start = end - timedelta(days=days)
        response = self.session.getCandleData({
            "exchange": exchange,
            "symboltoken": str(token),
            "interval": interval,
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        })
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
        return candles
