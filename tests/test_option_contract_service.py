import unittest
from datetime import date, timedelta

from services.option_contract_service import buying_risk, contracts_near_spot, parse_front_month_future, parse_option_contracts


class OptionContractServiceTests(unittest.TestCase):
    def test_parses_current_index_options_and_normalizes_strikes(self):
        expiry = (date.today() + timedelta(days=7)).strftime("%d%b%Y").upper()
        rows = [
            {"token": "1", "symbol": "NIFTY26AUG25000CE", "name": "NIFTY", "expiry": expiry,
             "strike": "2500000.000000", "lotsize": "75", "instrumenttype": "OPTIDX", "exch_seg": "NFO"},
            {"token": "2", "symbol": "NIFTY26AUG25000PE", "name": "NIFTY", "expiry": expiry,
             "strike": "2500000.000000", "lotsize": "75", "instrumenttype": "OPTIDX", "exch_seg": "NFO"},
        ]
        contracts = parse_option_contracts(rows, "NIFTY")
        self.assertEqual(len(contracts), 2)
        self.assertEqual(contracts[0]["strike"], 25000)

    def test_buying_risk_uses_whole_lots(self):
        result = buying_risk(premium=100, lot_size=75, capital=100000, risk_percent=1)
        self.assertEqual(result["risk_cap"], 1000)
        self.assertEqual(result["per_lot_risk"], 7500)
        self.assertEqual(result["lots"], 0)

    def test_limits_contracts_to_atm_and_requested_wings(self):
        contracts = [
            {"strike": strike, "option_type": option_type}
            for strike in range(24000, 25051, 50) for option_type in ("CE", "PE")
        ]
        focused = contracts_near_spot(contracts, spot_price=24510, wings=5)
        self.assertEqual(len({contract["strike"] for contract in focused}), 11)
        self.assertEqual(len(focused), 22)

    def test_selects_nearest_active_index_future_for_volume_analysis(self):
        near_expiry = (date.today() + timedelta(days=7)).strftime("%d%b%Y").upper()
        far_expiry = (date.today() + timedelta(days=35)).strftime("%d%b%Y").upper()
        rows = [
            {"token": "near", "symbol": "NIFTY26AUGFUT", "name": "NIFTY", "expiry": near_expiry,
             "instrumenttype": "FUTIDX", "exch_seg": "NFO"},
            {"token": "far", "symbol": "NIFTY26SEPFUT", "name": "NIFTY", "expiry": far_expiry,
             "instrumenttype": "FUTIDX", "exch_seg": "NFO"},
        ]
        future = parse_front_month_future(rows, "NIFTY")
        self.assertEqual(future["token"], "near")
