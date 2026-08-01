from dataclasses import dataclass


@dataclass
class Trade:

    # Trade Information
    trade_date: str
    trade_time: str

    market: str
    symbol: str
    expiry: str

    strike: str
    option: str

    # Price
    entry: float
    exit: float
    stoploss: float
    target: float

    quantity: int

    pnl: float = 0.0
    rr_ratio: float = 0.0

    # Strategy
    setup: str = ""

    # Market Confirmation
    trend: bool = False
    vwap: bool = False
    ema: bool = False
    volume: bool = False
    oi: bool = False

    # Psychology
    psychology_before: str = ""
    psychology_after: str = ""

    # Review
    mistake: str = ""
    confidence: int = 0

    # AI
    ai_score: int = 0
    ai_decision: str = ""
    ai_review: str = ""

    # Notes
    notes: str = ""
    screenshot: str = ""