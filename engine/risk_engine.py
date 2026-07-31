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