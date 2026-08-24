# TPS AI Trading Assistant — Release 1.4.4

Release date: 21 August 2026

## What changed

- Added a combined late-entry and exhausted-range safeguard after the 24 August evidence audit. A fresh pullback trigger no longer receives grace when price is already beyond the preferred ATR extension and the VIX-implied daily movement budget is consumed.
- Entry audit text now includes expected-range utilization, remaining movement points and movement state. Normal fresh-trigger grace is unchanged while sufficient movement budget remains.
- Option Strategies now labels the current-expiry candidate side as CE, PE or Hedged Range.
- Every valid defined-risk structure shows maximum potential profit, a conservative paper target-profit reference, loss-review reference and defined maximum loss.
- Saved strategies are checked every completed 5-minute cycle using conservative executable bid/ask quotes.
- A confirmed CE-to-PE or PE-to-CE thesis reversal first lists every close leg for the old structure and only then lists an optional opposite-side replacement.
- Replacement expiry and strategy are recorded, and uncovered option selling remains prohibited.
- Risk cap, liquidity, spread, late-session, extreme-VIX and no-naked-option safeguards remain active.
- Cutie is the friendly guidance voice for strategy analysis and key alerts; TPS AI Trading Assistant remains the product name.
- Strategy Health now distinguishes DO NOTHING, WATCH, PREPARE HEDGE ADJUSTMENT, BOOK PAPER TARGET, CUT RISK and EXIT & SWITCH SIDE.
- Any optional replacement shows its expiry, paper target reference and defined maximum loss after the old structure's close-first instructions.

TPS remains read-only decision-support and paper-validation software. Release 1.4.4 does not place, modify or cancel broker orders. Target profit is not guaranteed.
