import unittest
from unittest.mock import patch

import pandas as pd

from invest_app.dividends import (
    _dividend_business_key,
    _dividend_estimate_from_group,
    _roll_estimate_after_recorded_period,
    _shift_dividend_date_month,
)


class DividendRollForwardTests(unittest.TestCase):
    def test_shift_month_clamps_end_of_month(self):
        self.assertEqual(_shift_dividend_date_month("2026/01/31"), "2026/02/28")

    def test_recorded_period_rolls_to_next_month(self):
        estimate = {
            "platform": "基富通",
            "fund_code": "acft94",
            "currency": "TWD",
            "fund_name": "富蘭克林華美新興國家固定收益基金B-新臺幣",
            "ex_date": "2026/10/01",
            "pay_date": "2026/10/13",
        }
        current_key = _dividend_business_key(
            estimate["fund_code"], estimate["platform"], estimate["currency"],
            estimate["fund_name"], estimate["ex_date"], estimate["pay_date"],
        )
        rolled = _roll_estimate_after_recorded_period(estimate, {current_key})
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


if __name__ == "__main__":
    unittest.main()
