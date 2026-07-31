class TrendEngine:

    def evaluate(

        self,

        ema20,

        ema50,

        price

    ):

        if price > ema20 > ema50:
            return True

        return False