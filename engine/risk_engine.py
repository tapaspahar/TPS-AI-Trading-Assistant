class RiskEngine:

    def calculate_position_size(
        self,
        capital,
        risk_percent,
        entry,
        stoploss
    ):

        risk_amount = capital * (risk_percent / 100)

        risk_per_share = abs(entry - stoploss)

        if risk_per_share == 0:
            return 0

        quantity = risk_amount / risk_per_share

        return int(quantity)

    def assess_option_risk(
        self, *, capital, risk_percent, daily_loss_percent, max_trades_per_day,
        trades_today, open_trades, realized_pnl, entry, stoploss, target,
        lot_size, requested_lots,
    ):
        """Assess a long option plan in whole lots without placing an order."""
        values = (capital, risk_percent, daily_loss_percent, entry, stoploss, target, lot_size, requested_lots)
        if any(float(value) < 0 for value in values) or capital <= 0 or lot_size < 1 or requested_lots < 1:
            raise ValueError("Use positive plan values and at least one lot.")
        if not 0 < risk_percent <= 100 or not 0 < daily_loss_percent <= 100:
            raise ValueError("Risk percentages must be between 0 and 100.")
        if stoploss >= entry or target <= entry:
            raise ValueError("For option buying, stop loss must be below entry and target above entry.")

        trade_risk_cap = capital * risk_percent / 100
        daily_loss_limit = capital * daily_loss_percent / 100
        realized_loss = max(0.0, -float(realized_pnl))
        daily_remaining = max(0.0, daily_loss_limit - realized_loss)
        risk_per_unit = entry - stoploss
        reward_per_unit = target - entry
        risk_per_lot = risk_per_unit * int(lot_size)
        available_risk = min(trade_risk_cap, daily_remaining)
        safe_lots = int(available_risk // risk_per_lot) if risk_per_lot else 0
        planned_risk = risk_per_lot * int(requested_lots)
        blockers = []
        if int(trades_today) >= int(max_trades_per_day):
            blockers.append("maximum trades for today reached")
        if int(open_trades) > 0:
            blockers.append("an option paper trade is already open")
        if daily_remaining <= 0:
            blockers.append("daily loss limit exhausted")
        if safe_lots < 1:
            blockers.append("one lot exceeds the available risk budget")

        rr_ratio = reward_per_unit / risk_per_unit
        if blockers:
            verdict = "BLOCKED"
        elif requested_lots > safe_lots:
            verdict = "REDUCE LOTS"
        elif rr_ratio < 1.5:
            verdict = "REVIEW"
        else:
            verdict = "SAFE"
        return {
            "verdict": verdict,
            "blockers": blockers,
            "trade_risk_cap": trade_risk_cap,
            "daily_loss_limit": daily_loss_limit,
            "daily_remaining": daily_remaining,
            "risk_per_unit": risk_per_unit,
            "risk_per_lot": risk_per_lot,
            "planned_risk": planned_risk,
            "safe_lots": safe_lots,
            "quantity": int(requested_lots) * int(lot_size),
            "rr_ratio": rr_ratio,
        }
