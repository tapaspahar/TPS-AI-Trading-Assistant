# TPS AI Trading Assistant 1.4.6

Release date: 26-08-2026

- Added the Strategy Trades paper-validation workspace.
- Evaluates a catalog of defined-risk directional and range strategies against live option-chain quotes.
- Saves simulated strategy captures, live mark-to-market updates, exits and outcome explanations.
- Shows strategy history inside Trade Journal and a performance leaderboard for comparison.
- Keeps uncovered short-option structures disabled and treats unlimited-profit long-volatility structures as comparison-only candidates.
- Compares up to 30 distinct strike combinations instead of one fixed strike set.
- Adds friendly Cutie strategy names, estimated defined-risk capital, entry cashflow and model return-on-capital.
- Groups forward outcomes by market regime so TPS can learn which structure worked in comparable conditions.
- Records the friendly strategy name and fund estimate in Strategy Trades and Trade Journal.
- Keeps live Defined-Risk Strategies and VIX/ATR Intelligence exclusively on Option Strategies; Strategy Trades is now a dedicated captured-trade ledger.
- Shows capture score and scenario score on every saved strategy trade.
- Ranks strategies by actual closed-paper win rate, then sample count and total P&L, with the top rank first.
- Observes the configured market's first 15 minutes before starting automatic strategy checking.
- Places up to 30 unique bounded-risk strike combinations into paper-validation monitoring; repeated candles no longer duplicate the same combination.
- Automatically closes remaining paper strategies at market close and stores a date-wise Cutie review with market direction/regime, profitable/loss counts and best/worst structures.
- Adds a permanent market-close learning table so comparable future regimes can reference actual historical paper outcomes.

TPS remains a research and paper-validation application. It does not guarantee profit or place broker orders.
