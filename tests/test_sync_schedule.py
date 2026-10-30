import unittest
from datetime import datetime, timedelta, timezone

from invest_app.sync_schedule import JOBS, is_stale, last_slot, run_updated

TZ = timezone(timedelta(hours=8))
JOB = {job.key: job for job in JOBS}


def at(day, hour, minute):
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)  # 2026-11-02 = Monday


class SyncScheduleTests(unittest.TestCase):
    def test_tw_slots_follow_trading_hours(self):
        self.assertEqual(last_slot(at(2, 10, 44), JOB["tw"]), at(2, 10, 40))
        self.assertEqual(last_slot(at(2, 16, 0), JOB["tw"]), at(2, 14, 30))
        self.assertEqual(last_slot(at(2, 8, 0), JOB["tw"]), datetime(2026, 10, 30, 14, 30, tzinfo=TZ))  # Friday

    def test_tw_allows_one_missed_run(self):
        tw = JOB["tw"]
        self.assertFalse(is_stale(tw, at(2, 10, 21), at(2, 10, 44)))  # 10:30 missed, 10:20 ran
        self.assertTrue(is_stale(tw, at(2, 10, 11), at(2, 10, 44)))   # 10:20 and 10:30 missed
        self.assertFalse(is_stale(tw, datetime(2026, 10, 30, 14, 30, tzinfo=TZ), at(2, 8, 33)))  # 08:30 still running
        self.assertFalse(is_stale(tw, at(2, 14, 30), at(2, 20, 0)))
        self.assertTrue(is_stale(tw, None, at(2, 10, 0)))
        # window just reopened: only Monday 08:30 missed, Friday 14:30 is the previous slot
        friday_close = datetime(2026, 10, 30, 14, 30, 20, tzinfo=TZ)
        self.assertFalse(is_stale(tw, friday_close, at(2, 8, 44)))
        self.assertTrue(is_stale(tw, friday_close, at(2, 8, 54)))

    def test_us_window_crosses_midnight(self):
        us = JOB["us"]
        self.assertEqual(last_slot(at(3, 3, 10), us), at(3, 3, 0))
        self.assertEqual(last_slot(at(2, 12, 0), us), datetime(2026, 10, 31, 6, 0, tzinfo=TZ))  # Saturday 06:00
        self.assertFalse(is_stale(us, at(3, 2, 31), at(3, 3, 10)))
        self.assertTrue(is_stale(us, at(3, 1, 31), at(3, 3, 10)))
        self.assertFalse(is_stale(us, datetime(2026, 10, 31, 6, 0, tzinfo=TZ), at(2, 12, 0)))

    def test_only_real_updates_count(self):
        tw, us = JOB["tw"], JOB["us"]
        self.assertFalse(run_updated(tw, "dry-run", at(2, 10, 0)))
        self.assertTrue(run_updated(tw, "update", at(2, 20, 0)))         # app-dispatched
        self.assertTrue(run_updated(tw, "auto", at(2, 14, 38)))          # delayed 14:30 trigger
        self.assertFalse(run_updated(tw, "auto", at(2, 14, 40)))         # skipped outside window
        self.assertFalse(run_updated(tw, "auto", at(2, 8, 20)))
        self.assertFalse(run_updated(us, "Taiwan stock prices", at(3, 6, 30)))  # old run, no run-name
        self.assertTrue(run_updated(us, "auto", at(3, 6, 5)))

    def test_fund_runs_all_day(self):
        fund = JOB["fund"]
        self.assertFalse(is_stale(fund, at(2, 9, 31), at(2, 10, 10)))
        self.assertTrue(is_stale(fund, at(2, 8, 59), at(2, 10, 10)))


if __name__ == "__main__":
    unittest.main()
