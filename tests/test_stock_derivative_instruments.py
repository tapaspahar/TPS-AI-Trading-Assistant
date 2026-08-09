import unittest
from datetime import date, timedelta

from services.option_contract_service import (
    parse_stock_front_month_future, parse_stock_option_contracts, parse_stock_option_universe,
)


class StockDerivativeInstrumentTests(unittest.TestCase):
    def setUp(self):
        expiry = (date.today() + timedelta(days=15)).strftime("%d%b%Y").upper()
        self.rows = [
            {"name": "RELIANCE", "symbol": "RELIANCE-EQ", "token": "cash", "exch_seg": "NSE", "instrumenttype": ""},
            {"name": "RELIANCE", "symbol": f"RELIANCE{expiry}2500CE", "token": "ce", "exch_seg": "NFO", "instrumenttype": "OPTSTK", "expiry": expiry, "strike": "250000", "lotsize": "250"},
            {"name": "RELIANCE", "symbol": f"RELIANCE{expiry}2500PE", "token": "pe", "exch_seg": "NFO", "instrumenttype": "OPTSTK", "expiry": expiry, "strike": "250000", "lotsize": "250"},
            {"name": "RELIANCE", "symbol": f"RELIANCE{expiry}FUT", "token": "fut", "exch_seg": "NFO", "instrumenttype": "FUTSTK", "expiry": expiry, "lotsize": "250"},
            {"name": "NOOPTION", "symbol": "NOOPTION-EQ", "token": "cash2", "exch_seg": "NSE", "instrumenttype": ""},
        ]

    def test_universe_contains_only_cash_stocks_with_active_options(self):
        universe = parse_stock_option_universe(self.rows)
        self.assertEqual([(row["underlying"], row["token"]) for row in universe], [("RELIANCE", "cash")])

    def test_stock_contracts_and_future_are_normalized(self):
        contracts = parse_stock_option_contracts(self.rows, "RELIANCE")
        self.assertEqual({row["option_type"] for row in contracts}, {"CE", "PE"})
        self.assertEqual({row["strike"] for row in contracts}, {2500.0})
        future = parse_stock_front_month_future(self.rows, "RELIANCE")
        self.assertEqual((future["token"], future["lot_size"]), ("fut", 250))
