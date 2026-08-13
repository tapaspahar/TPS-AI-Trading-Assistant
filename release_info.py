"""Application release metadata kept in one place."""

APP_NAME = "TPS AI Trading Assistant"
VERSION = "1.2.1"
DISPLAY_VERSION = "Release 1.2.1"
RELEASE_DATE = "12-08-2026"
PUBLISHER = "Tapas Kumar Pahar"

# Development-build metadata is separate from the published Release 1.0
# identity. Update this block whenever a reviewed application update is made.
SOFTWARE_UPDATE_VERSION = "v1.2.1"
LAST_UPDATED_AT = "13-08-2026 08:09:52 IST"
FOOTER_UPDATE_TEXT = "Software Update v1.2.1 - 13-08-2026 08:09 IST"
RELEASE_NOTES = (
    "Added Trend Memory Monitor with a permanent daily market-fingerprint database for trend, chart shape, Candle DNA, EMA/VWAP/SuperTrend, volume, RSI/ATR and OI-PCR context.",
    "Added live historical analog matching and an optional desktop alert when the developing session reaches 80% similarity with a completed saved market day, including that day's actual outcome.",
    "Published maintenance Release 1.2.1 with aligned application, Windows executable, installer, portable ZIP and Help Center version metadata.",
    "Expanded Gap Probability Lab into separate 3:20 actionable and 3:40 post-close confirmation forecasts shown together with CONFIRMED/CHANGED comparison.",
    "Added automatic selected-index capture near 3:20 PM and retry-safe closing recalculation at/after 3:40 PM when TPS is open and broker data is connected.",
    "Protected closing confirmation from weekends, stale broker candles and rapid repeated API retries; both stages remain independently auditable against the next market open.",
    "Made Help Center text, headings, links, safety notes and separators automatically follow every colour theme and UI design style with high-contrast reader colours.",
    "Help pages now refresh immediately during theme preview without requiring an application restart, while preserving the current reading position.",
    "Rebuilt Help Center as a complete 28-page offline manual in English, Roman Hindi and Hindi, with purpose, main controls, outputs and cautions for every workspace.",
    "Added route-aware Help links: clicking Open this page now jumps directly to the referenced TPS workspace and updates the active sidebar item.",
    "Upgraded Put-Call Ratio into Options Market Intelligence with ATM straddle expected move/range, focused-window Max Pain, bid/ask spread coverage, chain data-quality score and transparent context labels.",
    "Added live-premium Black-Scholes ATM IV/Greeks estimates when expiry inputs are safe, while clearly withholding estimates when data is incomplete.",
    "Added estimated whole-position Delta, Gamma, Theta and Vega to valid limited-risk option strategies, plus expected-move, Max-Pain and chain-quality evidence in strategy and automatic opportunity reports.",
    "Auto Opportunity Radar now discovers its own liquid, active candidates from the complete NSE F&O stock universe; a manual watchlist is no longer required.",
    "Added a rate-conscious two-stage scan: lightweight universe ranking by turnover, movement and intraday participation, followed by deep TPS candle, futures and option-chain validation only for the strongest shortlist.",
    "Added TPS Auto Opportunity Radar: an unattended completed-5-minute-candle scanner for NIFTY, BANKNIFTY, SENSEX, configured stock-option watches and Equity Research watchlists.",
    "Added a permanent opportunity audit with BUY/WAIT/ERROR state, instrument, entry, protective exit, two targets, quantity, R:R, score, evidence and rejection reasons.",
    "The radar reuses Powerful Engine and existing TPS/OI/liquidity gates, runs automatically after broker connection and every eligible five-minute cycle, and remains research/paper-only without broker order placement.",
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

