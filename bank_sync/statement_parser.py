"""讀信用卡電子帳單文字：本期應繳總額、繳款截止日、逐筆消費。

細帳月份規則（用 2026細帳 既有數字對過）：帳單記在「繳款截止日」那個月的欄位，金額為「本期應繳總額」。
  例：台新 10 月帳單（截止 10/17）100,309 → 2026-10；星展 9 月帳單（截止 10/09）780 → 2026-10。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

NUM = r"-?[\d,]+"


@dataclass
class Charge:
    day: date
    description: str
    amount: int
    card: str = ""

    @property
    def is_payment(self) -> bool:
        """繳卡費／自動扣繳（不是消費，不列入明細）。"""
        return self.amount < 0 and bool(re.search(r"扣繳|繳款|ACH|轉帳", self.description))


@dataclass
class Statement:
    bank: str
    due: date | None = None
    total_due: int | None = None
    charges: list[Charge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ledger_month(self) -> str:
        return f"{self.due.year}-{self.due.month:02d}" if self.due else ""

    @property
    def purchases(self) -> list[Charge]:
        return [c for c in self.charges if not c.is_payment]


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def _roc(text: str) -> date:
    """115/10/02 → 2026-10-02；2026/10/02 也可。"""
    y, m, d = (int(x) for x in re.split(r"[/年月日-]", text.strip())[:3])
    return date(y + 1911 if y < 1911 else y, m, d)


def _clean(desc: str) -> str:
    return re.sub(r"\s{2,}", " ", desc).strip()


# ---------------- 台新 ----------------
def parse_taishin(text: str) -> Statement:
    st = Statement("taishin")
    m = re.search(r"繳款截止日\s*(\d{3}/\d{2}/\d{2})", text)
    st.due = _roc(m.group(1)) if m else None
    m = re.search(r"本期累計應繳金額\s*(" + NUM + ")", text)
    st.total_due = _int(m.group(1)) if m else None
    card = ""
    row = re.compile(r"^(\d{3}/\d{2}/\d{2}) (\d{3}/\d{2}/\d{2}) (.+?) (" + NUM + r")"
                     r"(?:\s+\d{4})?(?:\s+[A-Z]{2})?(?:\s+[A-Z]{3}\s+[\d.,]+)?\s*$")
    in_detail = False
    for line in text.splitlines():
        if line.startswith("消費日 入帳起息日"):
            in_detail = True
            continue
        if not in_detail:
            continue
        c = re.search(r"卡號末四碼[:：](\d{4})", line)
        if c:
            card = c.group(1)
            continue
        r = row.match(line.strip())
        if r:
            st.charges.append(Charge(_roc(r.group(1)), _clean(r.group(3)), _int(r.group(4)), card))
    return st


# ---------------- 富邦 ----------------
def parse_fubon(text: str) -> Statement:
    st = Statement("fubon")
    m = re.search(r"(\d{3}/\d{2}/\d{2})\s+(\d{3}/\d{2}/\d{2})\s+[\d.]+%", text)  # 結帳日 繳款截止日 利率
    if not m:
        m = re.search(r"繳款期限[\s\S]{0,80}?(\d{3}/\d{2}/\d{2})", text)
        st.due = _roc(m.group(1)) if m else None
    else:
        st.due = _roc(m.group(2))
    m = re.search(r"本期應繳總額\s*(" + NUM + r")\s*元", text)
    st.total_due = _int(m.group(1)) if m else None
    card = ""
    row = re.compile(r"^(\d{3}/\d{2}/\d{2}) (.+?) (\d{3}/\d{2}/\d{2})(?: .*?)? (" + NUM + r")$")
    for line in text.splitlines():
        line = line.strip()
        c = re.search(r"末４碼\s*(\d{4})|末4碼\s*(\d{4})", line)
        if c:
            card = c.group(1) or c.group(2)
            continue
        r = row.match(line)
        if r:
            desc = re.sub(r"\s+\S*\*{3}\S*$", "", r.group(2))  # 去掉電話號碼遮罩尾巴
            st.charges.append(Charge(_roc(r.group(1)), _clean(desc), _int(r.group(4)), card))
        if line.startswith("本期應繳金額"):
            break
    return st


# ---------------- 星展 ----------------
def parse_dbs(text: str) -> Statement:
    st = Statement("dbs")
    m = re.search(r"繳交截止日[:：]\s*(\d{4})年(\d{2})月(\d{2})日", text)
    st.due = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    m = re.search(r"應繳總金額\s*(" + NUM + ")", text)
    st.total_due = _int(m.group(1)) if m else None
    card = ""
    row = re.compile(r"^(\d{4}/\d{2}/\d{2}) (\d{4}/\d{2}/\d{2}) (.+?) (" + NUM + r")$")
    start = re.compile(r"^\d{4}/\d{2}/\d{2} \d{4}/\d{2}/\d{2} ")
    lines = [l.strip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        c = re.search(r"卡號末4碼\s*(\d{4})", line)
        if c:
            card = c.group(1)
        # 一筆消費可能被拆成好幾行（商店名稱太長），接到出現金額為止
        if start.match(line) and not row.match(line):
            j = i + 1
            while j < len(lines) and j <= i + 3 and not start.match(lines[j]):
                line = f"{line} {lines[j]}"
                if re.fullmatch(NUM, lines[j]):
                    break
                j += 1
            i = j
        r = row.match(line)
        if r:
            desc = re.sub(r"\s*/\s*[A-Z]{2}(?:\s+\S+)*$", "", r.group(3))  # 去掉「/ TW Taipei」
            st.charges.append(Charge(_roc(r.group(1)), _clean(desc), _int(r.group(4)), card))
        i += 1
    return st


# ---------------- 國泰世華 ----------------
def parse_cathay(text: str) -> Statement:
    st = Statement("cathay")
    ym = re.search(r"信用卡帳單\s*(\d{3})年(\d{1,2})月", text)
    year = int(ym.group(1)) + 1911 if ym else date.today().year
    plain = "\n".join(l for l in text.splitlines() if "順延" not in l and "原為" not in l)
    m = re.search(r"繳款截止日[^\d]{0,10}(\d{3}/\d{2}/\d{2})", plain)
    if m:
        st.due = _roc(m.group(1))
    elif ym:
        st.due = date(year, int(ym.group(2)), 1)  # 無須繳款時沒有截止日，用帳單月份
        st.warnings.append("帳單沒有繳款截止日，月份用帳單年月")
    m = re.search(r"本期應繳總額\s*(" + NUM + ")", text)
    st.total_due = _int(m.group(1)) if m else None
    row = re.compile(r"^(\d{2}/\d{2}) (\d{2}/\d{2}) (.+?) (" + NUM + r") (\d{4})\b")
    bill_month = int(ym.group(2)) if ym else 12
    for line in text.splitlines():
        r = row.match(line.strip())
        if r:
            mm, dd = (int(x) for x in r.group(1).split("/"))
            y = year - 1 if mm > bill_month else year  # 跨年：12 月消費出現在 1 月帳單
            st.charges.append(Charge(date(y, mm, dd), _clean(r.group(3)), _int(r.group(4)), r.group(5)))
    return st


# ---------------- 渣打 ----------------
def decode_unic(text: str) -> str:
    """渣打 PDF 的字型抽出來是 /UNIC0024 這種代碼；還原成字元（中文字型無對照，只剩數字與英文）。"""
    return re.sub(r"/UNIC([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), text)


def parse_sc(text: str) -> Statement:
    st = Statement("sc")
    t = decode_unic(text)
    # 頁首金額依序為：上期、已繳、調整、本期消費合計、利息費用、本期應繳…；細帳記的是「本期消費金額合計」
    dollars = re.findall(r"^\$ ?(" + NUM + r")$", t, re.M)
    if len(dollars) >= 4:
        st.total_due = _int(dollars[3])
    else:
        m = re.search(r"NT\$\s*(" + NUM + ")", t)
        st.total_due = _int(m.group(1)) if m else None
    d = re.search(r"^(20\d{2})\n(\d{2})\n(\d{2})$", t, re.M)  # 第一組「年/月/日」是繳款截止日
    st.due = date(int(d.group(1)), int(d.group(2)), int(d.group(3))) if d else None
    st.warnings.append("渣打帳單讀不到逐筆明細（PDF 文字只有數字）：細帳只記本期消費合計，含信用卡表不分類")
    return st


PARSERS = {"taishin": parse_taishin, "fubon": parse_fubon, "dbs": parse_dbs, "cathay": parse_cathay, "sc": parse_sc}


def parse(bank: str, text: str) -> Statement:
    st = PARSERS[bank](text)
    if st.total_due is None:
        st.warnings.append("找不到本期應繳總額")
    if st.due is None:
        st.warnings.append("找不到繳款截止日")
    if st.total_due is not None and st.charges:
        spent = sum(c.amount for c in st.purchases)
        if spent != st.total_due:
            st.warnings.append(f"逐筆消費合計 {spent:,} 與本期應繳 {st.total_due:,} 不同（可能有前期未繳餘額或漏讀，請確認）")
    return st


def note_text(st: Statement, stamp: date) -> str:
    """細帳格子備註：帳單摘要＋逐筆消費＋加註日期。"""
    names = {"taishin": "台新", "fubon": "富邦", "dbs": "星展", "cathay": "國泰世華", "sc": "渣打"}
    lines = [f"【{names.get(st.bank, st.bank)} 信用卡帳單】本期應繳 {st.total_due:,}" if st.total_due is not None
             else f"【{names.get(st.bank, st.bank)} 信用卡帳單】"]
    if st.due:
        lines.append(f"繳款截止日 {st.due:%Y/%m/%d}")
    for c in st.purchases:
        lines.append(f"{c.day:%m/%d} {c.description} {c.amount:,}")
    lines.append(f"加註日期：{stamp:%Y-%m-%d}（bank_sync）")
    return "\n".join(lines)
