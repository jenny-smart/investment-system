"""把信用卡帳單整理進總帳（2025Jenny-總帳）。

  2026細帳            ：金額不動，只在「信用卡-xx」那一列、繳款截止日那個月的格子加備註（逐筆消費＋加註日期）。
  2026細帳(含信用卡)  ：第一次執行時整張複製 2026細帳；每筆刷卡依分類規則，用「+金額」加進零用金各項，附備註。

預設只產生比對報表（不寫入）；加 --apply 才寫入，並對每個改到的格子發行事曆事件。
同一份帳單寫過就記在 statements/_ledger_applied.json，重跑不會重複加。
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .credentials import BANK_DIR, DEFAULT_CREDENTIALS_FILE, load_section
from .mail_statements import SOURCES, STATEMENT_DIR, open_pdf_text
from .statement_parser import Charge, Statement, note_text, parse

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
APPLIED_FILE = STATEMENT_DIR / "_ledger_applied.json"
RULES_FILE = BANK_DIR / "category_rules.json"
CARD_ROW_PREFIX = {"fubon": "信用卡-富邦", "taishin": "信用卡-台新", "sc": "信用卡-渣打",
                   "dbs": "信用卡-星展", "cathay": "信用卡-國泰世華"}
BANK_NAME = {"fubon": "富邦", "taishin": "台新", "sc": "渣打", "dbs": "星展", "cathay": "國泰世華"}
FALLBACK_ROW = "零用金-其他"

# 摘要關鍵字 → 細帳列名（第一個對到的為準）。可在 ~/Bank account/category_rules.json 覆寫或新增。
DEFAULT_RULES: list[tuple[str, str]] = [
    ("保險", "保費支出"), ("保費", "保費支出"), ("新壽", "保費支出"),
    ("電話費", "零用金-電話"), ("電信", "零用金-電話"), ("中華電", "零用金-電話"), ("台灣大哥大", "零用金-電話"),
    ("高鐵", "零用金-交通1"), ("台鐵", "零用金-交通1"), ("優步", "零用金-交通1"), ("UBER", "零用金-交通1"),
    ("大車隊", "零用金-交通1"), ("YOXI", "零用金-交通1"), ("計程車", "零用金-交通1"), ("纜車", "零用金-交通1"), ("捷運", "零用金-交通1"),
    ("停車", "零用金-交通1"), ("車旅", "零用金-交通1"), ("加油", "零用金-交通1"), ("悠遊", "零用金-交通1"),
    ("藥局", "零用金-醫療"), ("診所", "零用金-醫療"), ("醫院", "零用金-醫療"),
    ("書店", "零用金-書"), ("博客來", "零用金-書"),
    ("威秀", "零用金-電影"), ("影城", "零用金-電影"),
    ("超市", "零用金-食材"), ("全聯", "零用金-食材"), ("家樂福", "零用金-食材"),
    ("餐", "零用金-餐費"), ("飯", "零用金-餐費"), ("麵", "零用金-餐費"), ("早午餐", "零用金-餐費"),
    ("咖啡", "零用金-餐費"), ("CAF", "零用金-餐費"), ("茶", "零用金-餐費"), ("５０嵐", "零用金-餐費"), ("50嵐", "零用金-餐費"),
    ("烘焙", "零用金-餐費"), ("ＳＵＫＩＹＡ", "零用金-餐費"), ("鹽水雞", "零用金-餐費"),
    ("MOMO", "零用金-用品"), ("百貨", "零用金-用品"), ("特力", "零用金-用品"), ("康達盛通", "零用金-用品"),
    ("飯店", "零用金-旅行"), ("旅館", "零用金-旅行"), ("航空", "零用金-旅行"),
]


def load_rules(path: Path = RULES_FILE) -> list[tuple[str, str]]:
    """本機規則檔格式：[["關鍵字", "細帳列名"], ...]，排在預設規則前面（優先）。"""
    extra = []
    if path.exists():
        extra = [tuple(x) for x in json.loads(path.read_text("utf-8"))]
    return extra + DEFAULT_RULES


def categorize(description: str, rules: list[tuple[str, str]]) -> tuple[str, str]:
    """回傳 (列名, 依據)。對不到規則 → 零用金-其他。"""
    norm = lambda t: unicodedata.normalize("NFKC", t).upper()  # 全形 ＣＡＦ → CAF
    upper = norm(description)
    for keyword, row in rules:
        if norm(keyword) in upper:
            return row, f"規則：{keyword}"
    return FALLBACK_ROW, "對不到規則 → 待分類"


# ---------------------------------------------------------------- 讀帳單

@dataclass
class ParsedFile:
    bank: str
    path: Path
    statement: Statement

    @property
    def key(self) -> str:
        return f"{self.bank}:{self.path.name}"


def parsed_statements(year: int, path: Path = DEFAULT_CREDENTIALS_FILE, banks: tuple = ()) -> list[ParsedFile]:
    out = []
    for source in SOURCES:
        if source.code not in CARD_ROW_PREFIX or (banks and source.code not in banks):
            continue
        folder = STATEMENT_DIR / source.name
        if not folder.exists():
            continue
        try:
            password = load_section(source.code, ("pdf_password",), path)["pdf_password"]
        except (KeyError, ValueError):
            password = ""
        for pdf in sorted(list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))):
            try:
                st = parse(source.code, open_pdf_text(pdf, password))
            except Exception as exc:
                st = Statement(source.code, warnings=[f"打不開：{exc}"])
            if st.due and st.due.year != year:
                continue
            out.append(ParsedFile(source.code, pdf, st))
    return out


# ---------------------------------------------------------------- 試算表位置

def month_key(value) -> str:
    text = str(value).strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})(?:[/-]\d{1,2})?$", text)
    return f"{int(m.group(1))}-{int(m.group(2)):02d}" if m else ""


def month_columns(header_row: list) -> dict[str, int]:
    """第 1 列 → {"2026-04": 0-based 欄位}。"""
    return {k: i for i, v in enumerate(header_row) if (k := month_key(v))}


def find_row(labels: list, wanted: str, prefix: bool = False) -> int | None:
    """A 欄找列名（回傳 0-based）；prefix=True 時用開頭比對（例：信用卡-富邦 → 信用卡-富邦 19）。"""
    for i, v in enumerate(labels):
        text = str(v).strip()
        if text == wanted or (prefix and text.startswith(wanted)):
            return i
    return None


def a1(row0: int, col0: int) -> str:
    col, n = "", col0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        col = chr(65 + r) + col
    return f"{col}{row0 + 1}"


def to_number(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def add_term(formula: str, amount: int) -> str:
    """照 Jenny 的記法在格子後面接 +金額／-金額。"""
    term = f"+{amount}" if amount >= 0 else f"{amount}"
    f = str(formula or "").strip()
    if not f:
        return f"={amount}"
    if f.startswith("="):
        return f + term
    num = to_number(f)
    return f"={f.replace(',', '')}{term}" if num is not None else f + term


def merge_note(existing: str, block: str) -> str:
    """把同一份帳單的舊備註換成新的；其他內容保留。區塊以「【」開頭、以「（bank_sync）」結尾。"""
    head = "\n".join(block.splitlines()[:2])  # 第一行（銀行＋金額）＋第二行（繳款截止日）辨識同一份帳單
    kept = [b for b in re.split(r"\n(?=【)", existing or "") if b.strip() and not b.startswith(head)]
    return "\n".join(kept + [block]).strip()


# ---------------------------------------------------------------- 規劃（不寫入）

@dataclass
class CardAction:
    file: ParsedFile
    cell: str = ""
    current: float | None = None
    status: str = ""
    note: str = ""


@dataclass
class SpendAction:
    file: ParsedFile
    charge: Charge
    row_label: str
    reason: str
    cell: str = ""


@dataclass
class Plan:
    year: int
    cards: list[CardAction] = field(default_factory=list)
    spends: list[SpendAction] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def build_plan(files: list[ParsedFile], values: list[list], stamp: date, applied: dict) -> Plan:
    year = files[0].statement.due.year if files and files[0].statement.due else stamp.year
    plan = Plan(year)
    cols = month_columns(values[0] if values else [])
    labels = [r[0] if r else "" for r in values]
    rules = load_rules()
    for f in files:
        st = f.statement
        act = CardAction(f)
        plan.cards.append(act)
        if st.warnings and st.total_due is None:
            act.status = "讀不到帳單：" + "；".join(st.warnings)
            continue
        col = cols.get(st.ledger_month)
        row = find_row(labels, CARD_ROW_PREFIX[f.bank], prefix=True)
        if col is None or row is None:
            act.status = f"細帳找不到 {st.ledger_month} 欄或 {CARD_ROW_PREFIX[f.bank]} 列"
            continue
        act.cell = a1(row, col)
        raw = values[row][col] if row < len(values) and col < len(values[row]) else ""
        act.current = to_number(raw) if str(raw).strip() else None
        act.note = note_text(st, stamp)
        if act.current is None:
            act.status = "細帳空白（只加備註，金額請自行填）" if st.total_due else "細帳空白、帳單 0（不動）"
        elif round(act.current) == st.total_due:
            act.status = "相符（補備註）"
        else:
            act.status = f"不符：細帳 {act.current:,.0f}／帳單 {st.total_due:,}（只加備註，請確認）"
        if f.key in applied:
            act.status += "（已寫過，會更新備註）"
        for ch in st.purchases:
            if ch.amount == 0:
                continue
            label, reason = categorize(ch.description, rules)
            sa = SpendAction(f, ch, label, reason)
            r = find_row(labels, label)
            if r is None:
                sa.reason += f"；細帳沒有「{label}」列 → 改放 {FALLBACK_ROW}"
                sa.row_label = FALLBACK_ROW
                r = find_row(labels, FALLBACK_ROW)
            sa.cell = a1(r, col) if r is not None else ""
            plan.spends.append(sa)
        for w in st.warnings:
            plan.problems.append(f"{BANK_NAME[f.bank]} {f.path.name}：{w}")
    return plan


# ---------------------------------------------------------------- 報表

def write_report(plan: Plan, target: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "比對結果"
    ws.append(["卡", "帳單檔", "細帳月份", "2026細帳格子", "細帳現值", "帳單本期應繳", "逐筆合計", "狀態"])
    color = {"相符": "D9EAD3", "不符": "F4CCCC", "細帳空白": "FFF2CC", "讀不到": "F4CCCC"}
    for a in plan.cards:
        st = a.file.statement
        ws.append([BANK_NAME[a.file.bank], a.file.path.name, st.ledger_month, a.cell, a.current, st.total_due,
                   sum(c.amount for c in st.purchases), a.status])
        for k, c in color.items():
            if a.status.startswith(k):
                for cell in ws[ws.max_row]:
                    cell.fill = PatternFill("solid", fgColor=c)
    w2 = wb.create_sheet("消費明細與分類")
    w2.append(["卡", "細帳月份", "消費日", "摘要", "金額", "分類到（含信用卡表）", "格子", "依據"])
    for s in plan.spends:
        w2.append([BANK_NAME[s.file.bank], s.file.statement.ledger_month, s.charge.day.isoformat(),
                   s.charge.description, s.charge.amount, s.row_label, s.cell, s.reason])
        if "待分類" in s.reason or "沒有" in s.reason:
            for cell in w2[w2.max_row]:
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
    w3 = wb.create_sheet("備註預覽")
    w3.append(["2026細帳格子", "備註內容"])
    for a in plan.cards:
        if a.cell and a.note:
            w3.append([a.cell, a.note])
    if plan.problems:
        w4 = wb.create_sheet("需要確認")
        for p in plan.problems:
            w4.append([p])
    for sheet in wb:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    return target


# ---------------------------------------------------------------- 寫入

def open_book(creds):
    import gspread
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)


def ensure_copy(book, source_title: str, copy_title: str):
    titles = [w.title for w in book.worksheets()]
    if copy_title in titles:
        return book.worksheet(copy_title), False
    src = book.worksheet(source_title)
    return book.duplicate_sheet(src.id, insert_sheet_index=src.index + 1, new_sheet_name=copy_title), True


def apply_plan(plan: Plan, book, stamp: date, applied: dict, calendar=None) -> list[str]:
    """寫入：2026細帳 只加備註；含信用卡表加金額＋備註。回傳改到的格子說明。"""
    detail_title = f"{plan.year}細帳"
    copy_title = f"{plan.year}細帳(含信用卡)"
    detail = book.worksheet(detail_title)
    copy, created = ensure_copy(book, detail_title, copy_title)
    log = [f"已建立工作表「{copy_title}」"] if created else []
    events: list[tuple[str, str, str]] = []

    # 1) 2026細帳：信用卡格子只加備註
    old_notes = detail.get_notes()
    for a in plan.cards:
        if not a.cell or not a.note or a.status.startswith("細帳空白、帳單 0"):
            continue
        r, c = _rc(a.cell)
        existing = old_notes[r][c] if r < len(old_notes) and c < len(old_notes[r]) else ""
        merged = merge_note(existing, a.note)
        if merged != existing:
            detail.update_note(a.cell, merged)
            log.append(f"{detail_title}!{a.cell} 加備註（{a.status}）")
            events.append((f"{detail_title}!{a.cell}:{a.file.key}",
                           f"【細帳備註】{a.file.statement.ledger_month} {CARD_ROW_PREFIX[a.file.bank]}",
                           f"{detail_title}!{a.cell}｜{a.status}\n{a.note}"))

    # 2) 含信用卡表：刷卡加進零用金各項（同一份帳單只加一次）
    pending = [s for s in plan.spends if s.cell and s.file.key not in applied]
    by_cell: dict[str, list[SpendAction]] = {}
    for s in pending:
        by_cell.setdefault(s.cell, []).append(s)
    if by_cell:
        formulas = copy.get_values(value_render_option="FORMULA")
        notes = copy.get_notes()
        for cell, items in by_cell.items():
            r, c = _rc(cell)
            formula = formulas[r][c] if r < len(formulas) and c < len(formulas[r]) else ""
            new = formula
            for s in items:
                new = add_term(new, s.charge.amount)
            lines = [f"{BANK_NAME[s.file.bank]} {s.charge.day:%m/%d} {s.charge.description} {s.charge.amount:,}"
                     + ("（待分類）" if "待分類" in s.reason else "") for s in items]
            block = f"【信用卡 {items[0].file.statement.ledger_month}】\n" + "\n".join(lines) + f"\n加註日期：{stamp:%Y-%m-%d}（bank_sync）"
            existing = notes[r][c] if r < len(notes) and c < len(notes[r]) else ""
            copy.update(range_name=cell, values=[[new]], value_input_option="USER_ENTERED")
            copy.update_note(cell, (existing + "\n" + block).strip() if existing else block)
            log.append(f"{copy_title}!{cell} {formula or '（空白）'} → {new}")
            events.append((f"{copy_title}!{cell}:{stamp}:{len(items)}:{items[0].file.key}",
                           f"【細帳(含信用卡)】{items[0].file.statement.ledger_month} {items[0].row_label} +{sum(s.charge.amount for s in items):,}",
                           f"{copy_title}!{cell}：{formula or '（空白）'} → {new}\n" + "\n".join(lines)
                           + f"\n加註日期：{stamp:%Y-%m-%d}"))
    for s in pending:
        applied[s.file.key] = stamp.isoformat()
    for a in plan.cards:
        if a.cell:
            applied.setdefault(a.file.key, stamp.isoformat())

    if calendar:
        for key, title, body in events:
            calendar(key, stamp, title, body)
    return log


def _rc(cell: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", cell)
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, col - 1


def load_applied() -> dict:
    return json.loads(APPLIED_FILE.read_text("utf-8")) if APPLIED_FILE.exists() else {}


def save_applied(data: dict) -> None:
    APPLIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def run(year: int, apply: bool = False, banks: tuple = ()) -> Path:
    stamp = date.today()
    files = parsed_statements(year, banks=banks)
    if not files:
        raise SystemExit(f"{STATEMENT_DIR} 裡沒有 {year} 年的帳單；先執行 fetch-statements --months 12")
    from .google_auth import calendar_add_once, credentials
    creds = credentials()
    book = open_book(creds)
    values = book.worksheet(f"{year}細帳").get_values()
    applied = load_applied()
    plan = build_plan(files, values, stamp, applied)
    report = write_report(plan, STATEMENT_DIR / f"_細帳比對_{stamp:%Y%m%d}.xlsx")
    for a in plan.cards:
        print(f"{BANK_NAME[a.file.bank]} {a.file.statement.ledger_month} {a.cell or '-'}：{a.status}")
    print(f"刷卡 {len(plan.spends)} 筆，其中待分類 {sum('待分類' in s.reason for s in plan.spends)} 筆")
    print(f"比對報表：{report}")
    if not apply:
        print("（只比對，沒有寫入。確認報表後加 --apply 才會寫入總帳。）")
        return report
    calendar = lambda key, day, title, body: print(
        "   行事曆：", title, "→", calendar_add_once(creds, "bank_sync:" + key, day, title, body))
    for line in apply_plan(plan, book, stamp, applied, calendar):
        print("✓", line)
    save_applied(applied)
    return report
