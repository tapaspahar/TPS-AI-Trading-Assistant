# TPS AI Trading Assistant 1.5.2

- Expiry-day ATM CE+PE premium-parity trigger after 3:00 PM.
- Closest ATM, same strike and one quote snapshot; maximum premium gap ₹10.
- Duplicate-safe paired intent with combined target, maximum-loss and time exit monitoring.
- PAPER remains the default. REAL requires the existing session authorization and both-leg preflight.
- Two broker orders cannot be guaranteed to fill at the identical exchange timestamp; partial fills invoke cancel/protective-unwind handling.
