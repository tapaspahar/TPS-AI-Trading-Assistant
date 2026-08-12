"""Application release metadata kept in one place."""

APP_NAME = "TPS AI Trading Assistant"
VERSION = "1.2.0"
DISPLAY_VERSION = "Release 1.2"
RELEASE_DATE = "12-08-2026"
PUBLISHER = "Tapas Kumar Pahar"

# Development-build metadata is separate from the published Release 1.0
# identity. Update this block whenever a reviewed application update is made.
SOFTWARE_UPDATE_VERSION = "v1.2.0"
LAST_UPDATED_AT = "12-08-2026 14:56:49 IST"
FOOTER_UPDATE_TEXT = "Software Update v1.2.0 - 12-08-2026 14:56 IST"
RELEASE_NOTES = (
    "Added a separate 3:20 Gap Probability Lab for NIFTY, BANKNIFTY and SENSEX with Gap Up, Flat and Gap Down probabilities.",
    "Combined completed Spot/Future trend, futures basis, OI-PCR and optional latest-published official FII/FPI and DII cash flow without inventing unavailable values.",
    "Added permanent forecast history and automatic next-session open verification so TPS can show measured sample accuracy instead of claiming guaranteed prediction.",
    "Protected saved settings across source updates, new builds and installer upgrades with AppData migration, atomic writes and automatic backup recovery.",
    "Added support/resistance proximity alerts when live price enters or crosses the chart levels marked by TPS.",
    "Added a Put-Call Ratio & OI Observer for Call OI, Put OI, change in OI, OI-PCR, Volume-PCR, OI walls and explainable sentiment context.",
    "Added a central Windows desktop Notification Center with a global switch, sound control and page/event-wise alert controls.",
    "Added desktop alerts for paper-trade capture, exit, target, stop loss, Open Trade Guard, market-structure changes and completed post-market reports.",
    "Added TPS Powerful Engine, a selective CE/PE signal controller combining Candle DNA purity, 5m/15m/1h structure, EMA/VWAP/SuperTrend, price action, volume, VIX, OI and ATM liquidity.",
    "Powerful Engine abstains on conflicting, missing, unvalidated or illiquid evidence and keeps confluence strength separate from historically measured prediction purity.",
    "Added the experimental Pre-Candle Probability Lab with Candle DNA analog matching, bullish/bearish/range probabilities and a configurable 50-95% publication gate.",
    "Added expanding walk-forward purity validation so a next-candle signal is hidden until at least 15 eligible out-of-sample historical predictions clear the selected purity threshold.",
    "Added an official read-only Paytm Money adapter with browser authorization, secure token storage, instrument mapping, quotes, candles, OI and live-price support.",
    "Made Dhan authentication rate-safe so market-data permission failures no longer trigger a second token within two minutes, and inactive Data API plans are explained clearly.",
    "Added a complete read-only Dhan adapter with automatic daily access-token renewal, instrument mapping, candles, quotes, OI and live price updates.",
    "Added CAS Analysis and Stock Options Watch workspaces.",
    "Added adaptive market-regime rules and limited-risk Option Strategies.",
    "Refined Market Snapshot cards so values remain separated and readable.",
    "Added reliable mouse-wheel scrolling and visible scrollbar arrow controls.",
    "Made 'No known high-impact event' the default Options Workspace event status.",
    "Added visible software-update metadata and dated Help Center release notes.",
    "Added permanent date-wise Roman Hindi 'Post Market Analysis of TPS' journal.",
    "Made TPS post-market reports generate automatically after market close with restart backfill.",
)

