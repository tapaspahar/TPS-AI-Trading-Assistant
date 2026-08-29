# TPS AI Trading Assistant 1.5.1

- Capital Guardian defaults for new installations: 0.25% per-trade risk and 0.5% daily loss limit. Existing settings are preserved.
- Adaptive option-premium stops use volatility regime, liquidity spread and a bounded wick/sweep buffer.
- Wider stops reduce whole-lot quantity; TPS rejects the setup if one lot exceeds the rupee-risk cap.
- Stop evidence is attached to every generated review plan so post-market analysis can distinguish an ordinary wick/sweep from genuine setup invalidation.
- No stop placement or strategy guarantees profit; market, broker and risk locks remain active.
