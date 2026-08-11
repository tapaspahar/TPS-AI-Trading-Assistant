"""Application release metadata kept in one place."""

APP_NAME = "TPS AI Trading Assistant"
VERSION = "1.1.0"
DISPLAY_VERSION = "Release 1.1"
RELEASE_DATE = "10-08-2026"
PUBLISHER = "Tapas Kumar Pahar"

# Development-build metadata is separate from the published Release 1.0
# identity. Update this block whenever a reviewed application update is made.
SOFTWARE_UPDATE_VERSION = "v1.1.0"
LAST_UPDATED_AT = "11-08-2026 08:35:13 IST"
FOOTER_UPDATE_TEXT = "Software Update v1.1.0 • 11-08-2026 08:35 IST"
RELEASE_NOTES = (
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

