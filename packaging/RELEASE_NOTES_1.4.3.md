# TPS AI Trading Assistant — Release 1.4.3

Release date: 20 August 2026

## What changed

- Corrected zero-capture over-blocking found in the 19 August report.
- Single-touch/fallback swing levels are observation warnings; they no longer become a moving hard wall on every 5-minute candle.
- Repeated chart zones and option-chain OI walls remain strict support/resistance safety blockers.
- Established TRENDING continuation can use normal directional participation when structure, VWAP, EMA stack and candle direction agree.
- Trend Memory uses whole-session EMA/VWAP persistence, preventing a late bounce from hiding a persistent uptrend or downtrend.
- Added targeted regression tests for every corrected decision path.

TPS remains read-only decision-support and paper-validation software. Release 1.4.3 does not place, modify or cancel broker orders.
