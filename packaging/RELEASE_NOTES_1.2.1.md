# TPS AI Trading Assistant — Release 1.2.1

Release date: 12-08-2026

## Highlights

- Added a permanent Notification Center with date/time, source category, title, complete message and read/unread status for every delivered TPS desktop alert.
- Added Today/All/Unread filters, sidebar unread count, full alert detail, mark-read actions and CSV export. Saved history remains in AppData across restarts and upgrades.
- Corrected SENSEX auto-paper confirmation so sparse futures-volume samples are excluded as unavailable evidence instead of being counted as a failed directional-volume signal.
- Kept EMA/SuperTrend checks active in calm sessions and added a bounded fresh-trigger grace band while retaining genuine execution and risk blockers.
- Added separate 3:20 PM actionable and 3:40 PM closing-confirmation gap forecasts on the same page.
- Added automatic selected-index capture, retry-safe closing recalculation and CONFIRMED/CHANGED comparison.
- Protected gap forecasts from weekends, stale broker candles and repeated API retries.
- Made Help Center text, headings, links and safety notes readable across every colour theme and UI style.
- Aligned the application title, About/Help metadata, Windows executable, installer, portable ZIP and checksums to Release 1.2.1.

## Upgrade behaviour

Installing Release 1.2.1 over an older release preserves the user's saved trading setup, theme, notification choices and securely stored broker credentials.

## Safety

TPS remains a read-only analysis and paper-trading assistant. It does not place, modify or cancel broker orders and does not guarantee returns. Verify live price, spread, liquidity, expiry, quantity, risk and event conditions before any manual action.
