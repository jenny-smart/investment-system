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


def test_next_parse_lines_synthetic():
    from bank_sync.next_tx import parse_lines
    lines = [":::", "主帳戶明細查詢", "剩餘時間: 09分 58秒",
             "金額新臺幣 $-1,000", "交易類型轉出", "明細描述轉出至測試帳戶", "摘要轉出", "交易時間2026/11/13 11:05", "備註說明無", "帳戶餘額新臺幣 $9,000",
             "金額新臺幣 $500", "交易類型轉入", "明細描述測試銀行-123", "摘要轉入", "交易時間2026/11/10 15:36", "備註說明uncle", "帳戶餘額新臺幣 $10,000"]
    rows = parse_lines(lines)
    assert rows == [["2026/11/13", "11:05", "轉出", "-1,000", "9,000", "轉出至測試帳戶", "", "轉出"],
                    ["2026/11/10", "15:36", "轉入", "500", "10,000", "測試銀行-123", "uncle", "轉入"]]
