import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from invest_app.dividends import (
    _dividend_estimate_from_group,
    _roll_estimate_to_next_period,
    _shift_dividend_date_month,
)


class DividendRollForwardTests(unittest.TestCase):
    def test_shift_month_clamps_end_of_month(self):
        self.assertEqual(_shift_dividend_date_month("2026/01/31"), "2026/02/28")

    def test_past_period_rolls_to_first_future_month(self):
        estimate = {
            "platform": "基富通",
            "fund_code": "acft94",
            "currency": "TWD",
            "fund_name": "富蘭克林華美新興國家固定收益基金B-新臺幣",
            "ex_date": "2026/09/01",
            "pay_date": "2026/09/13",
        }
        rolled = _roll_estimate_to_next_period(estimate, date(2026, 10, 14))
        self.assertEqual(rolled["ex_date"], "2026/11/01")
        self.assertEqual(rolled["pay_date"], "2026/11/13")
        self.assertEqual(rolled["display_date"], "2026/11/01")

    @patch("invest_app.dividends._get_gas_data")
    def test_latest_announced_amount_beats_stored_amount(self, gas):
        gas.return_value = {
            "monthly_div": 0.043,
            "ex_date": "2026/09/30",
            "pay_date": "2026/10/13",
        }
        group = pd.DataFrame([{
            "platform": "基富通",
            "fund_code": "acft94",
            "currency": "TWD",
            "name": "富蘭克林華美新興國家固定收益基金B-新臺幣",
            "市值股數": 1000,
            "每單位月配息估算": 0.044,
            "monthly_dividend_per_unit": 0.044,
            "匯率": 1,
        }])
        estimate = _dividend_estimate_from_group(group, {})
        self.assertIsNotNone(estimate)
        self.assertEqual(estimate["div_per_unit"], 0.043)
        self.assertEqual(estimate["total_amount"], 43)

    @patch("invest_app.dividends._get_gas_data")
    def test_newer_record_amount_beats_older_source_amount(self, gas):
        gas.return_value = {
            "monthly_div": 0.044,
            "ex_date": "2026/08/31",
            "pay_date": "2026/09/10",
        }
        group = pd.DataFrame([{
            "platform": "基富通", "fund_code": "acft94", "currency": "TWD",
            "name": "富蘭克林華美新興國家固定收益基金B-新臺幣",
            "市值股數": 1000, "monthly_dividend_per_unit": 0.044, "匯率": 1,
        }])
        history = {("acft94", "基富通", "TWD"): [{
            "id": 1, "_source_table": "fund_dividends", "fund_code": "acft94",
            "platform": "基富通", "currency": "TWD", "ex_date": "2026/09/30",
            "pay_date": "2026/10/13", "actual_div_amount": 0.043, "div_amount": 0.043,
        }]}
        estimate = _dividend_estimate_from_group(group, history)
        self.assertEqual(estimate["div_per_unit"], 0.043)
        self.assertEqual(estimate["ex_date"], "2026/09/30")


if __name__ == "__main__":
    unittest.main()
