import unittest

from services.scalper_service import ScalperService


class ScalperContractSelectionTests(unittest.TestCase):
    def setUp(self):
        self.choices = [
            {"strike": strike, "symbol": f"NIFTY-{strike}"}
            for strike in (24450, 24500, 24550)
        ]

    def test_atm_selects_nearest_strike(self):
        selected = ScalperService._select_contract(self.choices, 24508, "CE", "ATM")
        self.assertEqual(selected["strike"], 24500)

    def test_ce_itm_and_otm_are_on_correct_side(self):
        self.assertEqual(ScalperService._select_contract(self.choices, 24500, "CE", "1-step ITM")["strike"], 24450)
        self.assertEqual(ScalperService._select_contract(self.choices, 24500, "CE", "1-step OTM")["strike"], 24550)

    def test_pe_itm_and_otm_are_on_correct_side(self):
        self.assertEqual(ScalperService._select_contract(self.choices, 24500, "PE", "1-step ITM")["strike"], 24550)
        self.assertEqual(ScalperService._select_contract(self.choices, 24500, "PE", "1-step OTM")["strike"], 24450)


if __name__ == "__main__":
    unittest.main()
