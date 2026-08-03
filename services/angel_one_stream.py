"""Background, read-only SmartAPI WebSocket stream."""
from threading import Thread


class AngelOneStream:
    def __init__(self, client, on_tick, on_status=lambda _status: None):
        self.client, self.on_tick, self.on_status = client, on_tick, on_status
        self.socket = None

    def start(self, exchange_type: int, token: str):
        if not getattr(self.client, "session", None):
            raise RuntimeError("Connect Angel One before starting a market feed.")
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except ImportError as error:
            raise RuntimeError("SmartAPI WebSocket dependency is unavailable.") from error
        self.socket = SmartWebSocketV2(self.client.auth_token, self.client.api_key, self.client.client_code, self.client.feed_token)
        self.socket.on_data = lambda _ws, message: self.on_tick(message)

        def report_error(_ws, error):
            text = str(error)
            if "connection closed" in text.lower():
                self.on_status("Live feed disconnected — reconnect when Angel One is available")
            else:
                self.on_status(f"Live feed issue: {text}")

        self.socket.on_error = report_error
        self.socket.on_close = lambda _ws: self.on_status("Feed disconnected")
        def open_feed(_ws):
            self.on_status("Live feed connected")
            self.socket.subscribe("tps-live-feed", 1, [{"exchangeType": exchange_type, "tokens": [str(token)]}])
        self.socket.on_open = open_feed
        Thread(target=self.socket.connect, daemon=True).start()

    def stop(self):
        if self.socket:
            self.socket.close_connection()
