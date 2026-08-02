"""Read-only Angel One SmartAPI session helper.

Credentials are supplied in memory by the UI and are never persisted here.
Order placement is intentionally out of scope.
"""

from __future__ import annotations


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
        return {"connected": True, "message": "Connected for read-only market data."}
