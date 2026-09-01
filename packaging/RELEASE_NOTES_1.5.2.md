# TPS AI Trading Assistant 1.5.2

- Expiry-day ATM CE+PE premium-parity trigger after 3:00 PM.
- Closest ATM, same strike and one quote snapshot; maximum premium gap ₹10.
- Duplicate-safe paired intent with combined target, maximum-loss and time exit monitoring.
- PAPER remains the default. REAL requires the existing session authorization and both-leg preflight.
- Two broker orders cannot be guaranteed to fill at the identical exchange timestamp; partial fills invoke cancel/protective-unwind handling.
- Central scheduler limits heavy analysis concurrency to three jobs, suppresses duplicates and staggers polling start times.
- Index candle/OI analysis now runs outside the UI thread; unchanged evidence tables are not rebuilt.
- Same-day instrument data and parsed contracts are shared in memory; SQLite WAL keeps report reads responsive during background saves.
- Options Workspace PAPER Testing Mode now captures up to 10 independently monitored samples/day even while another paper trade is open.
- A near-valid exploratory sample may miss at most two soft checklist items; direction, volume, data, event, liquidity, timing and risk hard blockers remain strict and are saved in the audit.
- Added one timestamped Market Data Hub for shared candle, quote and option-chain snapshots, cache hit/failure telemetry and forced-fresh final capture verification.
- Duplicate symbol/side/candle/strike/regime theses are no longer counted as independent accuracy samples, even when ten concurrent testing slots are available.
- Paper BUY entries prefer executable ask, monitored exits prefer executable bid, and saved net P&L deducts configured round-trip cost and slippage.
- Dashboard now includes a Today Control Center, Market Data freshness/cache health and a conservative Paper Accuracy Lab with Wilson lower bound, expectancy and profit factor.
- Strategy ranking now prioritizes evidence tier and conservative confidence before raw win rate, and shows independent days, max drawdown and average capital requirement.
