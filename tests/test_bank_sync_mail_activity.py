from bank_sync.mail_activity import classify


def test_classify_subjects():
    assert classify("約定轉帳結果通知") == "tx"
    assert classify("台北富邦行動銀行臺幣轉帳交易「成功」通知") == "tx"
    assert classify("台北富邦行動銀行預約臺幣轉帳交易生效結果通知") == "tx"
    assert classify("台新銀行行動銀行外幣綜存轉定存交易通知") == "tx"
    assert classify("台新銀行信託財產管理運用通知書─申購/加入2026/11/14") == "tx"
    assert classify("台新網路銀行/行動銀行登入成功通知") == "login"
    assert classify("【將來銀行通知】登入成功") == "login"
    assert classify("台北富邦行動銀行「預約臺幣轉帳」生效前提醒通知") == ""
    assert classify("台新銀行信託投資商品停損停利通知信2026/11/16") == ""
    assert classify("台新銀行綜合對帳單 2026年10月份") == ""
    assert classify("提醒您本期信用卡帳單繳款截止日快到了") == ""
    assert classify("LINE Bank 聯名信用卡申請 (申辦手續尚未完成喔！）") == ""
