from dataclasses import dataclass


@dataclass
class Trade:

    trade_date: str
    trade_time: str

    symbol: str
    strike: str
    option: str

    entry: float
    exit: float

    quantity: int

    stoploss: float
    target: float

    psychology: str

    notes: str

    trend: bool = False
    vwap: bool = False
    ema: bool = False
    volume: bool = False
    oi: bool = False

    score: int = 0