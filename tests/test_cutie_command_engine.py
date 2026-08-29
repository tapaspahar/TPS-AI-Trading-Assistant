import unittest

from engine.cutie_command_engine import parse_cutie_command


class CutieCommandEngineTests(unittest.TestCase):
    def test_parses_complete_paper_algo_command(self):
        result = parse_cutie_command("NIFTY paper algo start target 1,000 max loss 500 max 3 trades 1 lot")
        self.assertEqual(result["intent"], "START_ALGO")
        self.assertEqual((result["mode"], result["symbol"]), ("PAPER", "NIFTY"))
        self.assertEqual((result["target"], result["max_loss"], result["max_trades"], result["lots"]), (1000, 500, 3, 1))

    def test_real_command_is_parsed_but_ui_can_fail_closed(self):
        result = parse_cutie_command("BANKNIFTY real algo start profit 2000 maximum loss 800 2 trades 1 lot")
        self.assertEqual(result["mode"], "REAL")

    def test_rejects_incomplete_and_bypass_commands(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_cutie_command("NIFTY paper algo start")
        with self.assertRaisesRegex(ValueError, "bypass"):
            parse_cutie_command("NIFTY paper algo start target 1000 loss 500 2 trades 1 lot bypass risk")

    def test_stop_and_status_are_allowlisted(self):
        self.assertEqual(parse_cutie_command("emergency stop")["intent"], "STOP_ALGO")
        self.assertEqual(parse_cutie_command("algo status")["intent"], "ALGO_STATUS")
