import unittest
from unittest import mock

import pandas as pd

import invest_app.dividends as d


def table():
    return pd.DataFrame([
        {"基金名稱": "東方匯理 U南非幣", "_確認前": False},
        {"基金名稱": "高盛 Y南非幣對沖", "_確認前": False},
        {"基金名稱": "富蘭克林華美", "_確認前": True},
    ])


class AutoConfirmTests(unittest.TestCase):
    def setUp(self):
        d.auto_confirm_state().clear()

    def run_with(self, plan, force=True):
        applied = {}

        def apply(df, changes, recompute_all=False):
            applied.update(changes)
            return len(changes), []

        with mock.patch.object(d, "build_actual_dividend_table", return_value=table()), \
             mock.patch.object(d, "ledger_plan_for", return_value=plan), \
             mock.patch.object(d, "apply_dividend_confirmations", side_effect=apply):
            state = d.auto_confirm_from_ledger(pd.DataFrame(), force=force)
        return state, applied

    def test_confirms_only_matched_pending_records(self):
        plan = [{"label": "配息-台新-南非", "ok": True, "candidates": [0, 1], "matched": [0]}]
        state, applied = self.run_with(plan)
        self.assertEqual(applied, {0: True})
        self.assertEqual(state["confirmed"], ["東方匯理 U南非幣"])
        self.assertEqual(state["waiting"], 1)

    def test_mismatch_confirms_nothing(self):
        plan = [{"label": "配息-台新-南非", "ok": False, "candidates": [0, 1], "matched": [0, 1]}]
        state, applied = self.run_with(plan)
        self.assertEqual(applied, {})
        self.assertEqual(state["mismatch"], ["配息-台新-南非"])

    def test_runs_at_most_every_10_minutes_unless_forced(self):
        plan = [{"label": "配息-台新-南非", "ok": True, "candidates": [0], "matched": [0]}]
        self.run_with(plan)
        _, applied = self.run_with(plan, force=False)
        self.assertEqual(applied, {})
        _, applied = self.run_with(plan, force=True)
        self.assertEqual(applied, {0: True})


if __name__ == "__main__":
    unittest.main()
