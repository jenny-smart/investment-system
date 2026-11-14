from datetime import date

from bank_sync.taishin_tx import _short, keep_new, parse_day, period_for


def test_short_masks_account_number():
    assert _short("2003-10-0001234-9 建北綜活儲存款") == "****349 建北綜活儲存款"


def test_parse_day_handles_roc_year():
    assert parse_day("2026/11/03") == date(2026, 11, 3)
    assert parse_day("115/11/03") == date(2026, 11, 3)
    assert parse_day("") is None


def test_period_for_picks_smallest_cover():
    today = date(2026, 11, 14)
    assert period_for(date(2026, 11, 10), today) == "7天"
    assert period_for(date(2026, 11, 1), today) == "14天"
    assert period_for(date(2026, 10, 1), today) == "2個月"


def test_keep_new_from_last_date_without_duplicates():
    rows = [["2026/11/01", "x", "a", "1"], ["2026/11/05", "x", "b", "2"], ["2026/11/05", "x", "c", "3"], ["2026/11/09", "x", "d", "4"]]
    first, state = keep_new(rows, {}, date(2026, 11, 2))
    assert [r[2] for r in first] == ["b", "c", "d"]
    assert state["last_date"] == "2026-11-09"
    again = rows + [["2026/11/09", "x", "e", "5"], ["2026/11/12", "x", "f", "6"]]
    second, state2 = keep_new(again, state, date(2026, 11, 2))
    assert [r[2] for r in second] == ["e", "f"]
    assert state2["last_date"] == "2026-11-12"
    third, state3 = keep_new(again, state2, date(2026, 11, 2))
    assert third == [] and state3["last_date"] == "2026-11-12"
