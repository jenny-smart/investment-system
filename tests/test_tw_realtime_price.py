import unittest


class PickMisPriceTests(unittest.TestCase):
    def test_last_trade(self):
        from invest_app.core import pick_mis_price
        self.assertEqual(pick_mis_price({"z": "170.5000", "y": "160.0000"}), (170.5, "TWSE即時"))

    def test_limit_up_locked_not_prev_close(self):
        from invest_app.core import pick_mis_price
        q = {"z": "-", "b": "735.0000_734.0000_", "a": "-", "u": "735.0000", "w": "602.0000", "y": "669.0000"}
        self.assertEqual(pick_mis_price(q), (735.0, "TWSE漲停"))

    def test_limit_down_locked(self):
        from invest_app.core import pick_mis_price
        q = {"z": "-", "b": "-", "a": "602.0000_603.0000_", "u": "735.0000", "w": "602.0000", "y": "669.0000"}
        self.assertEqual(pick_mis_price(q), (602.0, "TWSE跌停"))

    def test_no_trade_no_quote_leaves_prev_close_to_caller(self):
        from invest_app.core import pick_mis_price
        self.assertEqual(pick_mis_price({"z": "-", "b": "-", "a": "-", "y": "669.0000"}), (None, ""))


if __name__ == "__main__":
    unittest.main()
