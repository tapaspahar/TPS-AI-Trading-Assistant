# TPS AI Trading Assistant — Release 1.4.4

Release date: 21 August 2026

## What changed

- Option Strategies now labels the current-expiry candidate side as CE, PE or Hedged Range.
- Every valid defined-risk structure shows maximum potential profit, a conservative paper target-profit reference, loss-review reference and defined maximum loss.
- Saved strategies are checked every completed 5-minute cycle using conservative executable bid/ask quotes.
- A confirmed CE-to-PE or PE-to-CE thesis reversal first lists every close leg for the old structure and only then lists an optional opposite-side replacement.
- Replacement expiry and strategy are recorded, and uncovered option selling remains prohibited.
- Risk cap, liquidity, spread, late-session, extreme-VIX and no-naked-option safeguards remain active.

TPS remains read-only decision-support and paper-validation software. Release 1.4.4 does not place, modify or cancel broker orders. Target profit is not guaranteed.
