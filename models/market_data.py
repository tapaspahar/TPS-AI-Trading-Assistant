from dataclasses import dataclass


@dataclass
class MarketData:

    spot: float

    vwap: float

    ema20: float

    ema50: float

    volume: float

    average_volume: float

    oi: float

    pcr: float