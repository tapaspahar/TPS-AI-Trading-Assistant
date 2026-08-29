# TPS AI Trading Assistant 1.5.1

- Capital Guardian defaults for new installations: 0.25% per-trade risk and 0.5% daily loss limit. Existing settings are preserved.
- Adaptive option-premium stops use volatility regime, liquidity spread and a bounded wick/sweep buffer.
- Wider stops reduce whole-lot quantity; TPS rejects the setup if one lot exceeds the rupee-risk cap.
- Stop evidence is attached to every generated review plan so post-market analysis can distinguish an ordinary wick/sweep from genuine setup invalidation.
- No stop placement or strategy guarantees profit; market, broker and risk locks remain active.
- Broker Account Funds now refreshes after connection, on page open and every 60 seconds in the background; the last successful IST timestamp is visible and failed responses are explicitly marked non-current.
- Broker Funds now appears on the main Dashboard instead of the Broker Execution console, keeping the balance visible with the everyday overview while the execution page stays focused on safeguards and orders.
- Added Cutie AI Command Center for allow-listed Hindi/English PAPER algo start, status and emergency-stop commands. Incomplete, ambiguous and safeguard-bypass prompts are rejected.
- REAL prompt automation remains fail-closed until fill reconciliation and broker-managed exits are proven end to end; no free-form prompt can directly place an unrestricted order.
- Renamed the workspace to Cutie AI Assistant and added natural Hindi/English page navigation, including commands such as `jump to expiry after 3 pm page`, `show settings` and `go to strategy trades`.
- Added Limited REAL Pilot Mode with mandatory target/stop, maximum two accepted entries/day, quantity 65, 0.25% planned risk/trade and 0.5% recorded daily-loss ceilings.
- Added one-time daily REAL Pilot authorization from Cutie or Broker Execution. Once armed, structured orders can pass automatic preflight without repeating a confirmation phrase per trade; hard limits and mandatory exits still cannot be bypassed.
- Added OI Flow Intelligence with separate legacy OI and fresh COI ratios, small-base distortion filtering, premium/OI flow quadrants, adaptive near-money wings, dynamic CE/PE wall health, flow score and source-quality warnings.
