"""Paytm Money read-only price stream using rate-safe quote polling."""
from threading import Event, Thread


class PaytmMoneyStream:
    EXCHANGE_BY_TYPE = {1: "NSE", 3: "BSE"}

    def __init__(self, client, on_tick, on_status=lambda _status: None):
        self.client, self.on_tick, self.on_status = client, on_tick, on_status
        self._stop = Event()
        self._thread = None

    def start(self, exchange_type, token):
        if not getattr(self.client, "session", None):
            raise RuntimeError("Connect Paytm Money before starting a market feed.")
        exchange = self.EXCHANGE_BY_TYPE.get(int(exchange_type))
        if not exchange:
            raise RuntimeError("This Paytm Money live-feed exchange is unsupported.")
        self._stop.clear()

        def run():
            self.on_status("Paytm Money live feed connected")
            while not self._stop.wait(1.1):
                try:
                    quote = self.client.get_option_quote(exchange, str(token))
                    self.on_tick({"token": str(token), "last_traded_price": int(float(quote.get("ltp", 0)) * 100),
                                  "ltp": float(quote.get("ltp", 0))})
                except RuntimeError as error:
                    self.on_status(f"Paytm Money live feed issue: {error}")
            self.on_status("Paytm Money live feed disconnected")

        self._thread = Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
