# TPS AI Trading Assistant 1.4.8

Release date: 26-08-2026

- Option Strategies now has saved controls for today's combined Strategy Trades target profit and maximum loss.
- When either enabled paper limit is reached, every open Strategy Trade closes at its latest verified model P&L and fresh captures remain locked for that trading date.
- Strategy Trades shows today's combined P&L, configured limits and live guard state.
- A value of zero disables that limit. This remains paper validation only; no broker order is placed and no profit is guaranteed.
- Existing settings and local production records remain preserved across the update.
