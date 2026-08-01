from engine.tps_engine import TPSEngine
from models.trade import Trade


trade = Trade(

    trade_date="01-08-2026",

    trade_time="09:30",

    market="NIFTY",

    symbol="NIFTY",

    expiry="06-08-2026",

    strike="25000",

    option="CE",

    entry=120,

    exit=145,

    stoploss=100,

    target=180,

    quantity=75,

    setup="VWAP Breakout",

    trend=True,

    vwap=True,

    ema=True,

    volume=True,

    oi=True,

    psychology_before="Calm",

    psychology_after="Happy",

    mistake="",

    confidence=9,

    notes="Perfect Entry"

)

engine = TPSEngine()

result = engine.calculate(trade)

print(result)