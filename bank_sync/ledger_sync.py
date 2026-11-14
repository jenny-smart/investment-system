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
SKIP_ROW = "（不列零用金）"   # 只留在信用卡備註，不加進含信用卡表
TRAVEL_HINTS = ("PUSAN", "BUSAN", "SEOUL", "MIYAZA", "EHIME", "TOKYO", "TOUKIY", "LONDON", "LUXEMB", "BRUSSE",
                "GWACHE", "HONG K", "SINGAPORE", "WANCH", "OSAKA", "KYOTO", "FUKUOKA", "BANGKOK", "PARIS",
                "JP ", "KR ", "GB ", "/ SGP", "TRIP.COM", "AIRPORT", "HOTEL")

# 摘要關鍵字 → 細帳列名（第一個對到的為準，所以具體的放前面）。可在 ~/Bank account/category_rules.json 覆寫或新增。
DEFAULT_RULES: list[tuple[str, str]] = [
    # 不列零用金
    ("綜所稅", SKIP_ROW),
    # 公司代墊
    ("彭園", "零用金-公司代墊"), ("星全安", "零用金-公司代墊"), ("一零四資訊", "零用金-公司代墊"),
    ("ＬＩＮＥ 官方帳", "零用金-公司代墊"), ("LINE 官方帳", "零用金-公司代墊"),
    # 保費
    ("保險", "保費支出"), ("保費", "保費支出"), ("新壽", "保費支出"),
    # 其他（年費、折抵、退款、儲值、手續費）
    ("年費", "零用金-其他"), ("折抵", "零用金-其他"), ("回饋", "零用金-其他"), ("退款", "零用金-其他"),
    ("信用卡儲值", "零用金-其他"), ("繳費手續費", "零用金-其他"), ("Cofit", "零用金-其他"),
    # 拜拜
    ("華嚴寺", "零用金-拜拜"), ("寺", "零用金-拜拜"), ("宮", "零用金-拜拜"),
    # 家用
    ("有線電視", "零用金-家用"),
    # 電話
    ("電話費", "零用金-電話"), ("電信", "零用金-電話"), ("中華電", "零用金-電話"), ("台灣大哥大", "零用金-電話"),
    ("HINET", "零用金-電話"),
    # 交通
    ("重機養管", "零用金-交通2"),
    ("高鐵", "零用金-交通1"), ("台鐵", "零用金-交通1"), ("優步", "零用金-交通1"), ("UBER", "零用金-交通1"),
    ("大車隊", "零用金-交通1"), ("YOXI", "零用金-交通1"), ("計程車", "零用金-交通1"), ("纜車", "零用金-交通1"),
    ("捷運", "零用金-交通1"), ("停車", "零用金-交通1"), ("車旅", "零用金-交通1"), ("加油", "零用金-交通1"),
    ("悠遊", "零用金-交通1"), ("USPACE", "零用金-交通1"), ("旅電共享", "零用金-交通1"),
    # 醫療
    ("藥局", "零用金-醫療"), ("診所", "零用金-醫療"), ("醫院", "零用金-醫療"), ("愷達生醫", "零用金-醫療"),
    ("眼鏡", "零用金-醫療"), ("YAKKYOKU", "零用金-醫療"),
    # 化妝保養＋按摩（含醫美、皮拉提斯）
    ("JEIRINMEDI", "零用金-化妝保養＋按摩"), ("整復", "零用金-化妝保養＋按摩"), ("足體", "零用金-化妝保養＋按摩"),
    ("按摩", "零用金-化妝保養＋按摩"), ("LUSH", "零用金-化妝保養＋按摩"), ("Tobeysimple", "零用金-化妝保養＋按摩"),
    ("pd pila", "零用金-化妝保養＋按摩"), ("Pd忠孝館", "零用金-化妝保養＋按摩"), ("美業", "零用金-化妝保養＋按摩"),
    # 衣飾
    ("女人夢想堂", "零用金-衣飾"), ("MITSUI", "零用金-衣飾"), ("NET", "零用金-衣飾"), ("OLIVE YOUNG", "零用金-衣飾"),
    # 書／電影
    ("書店", "零用金-書"), ("博客來", "零用金-書"),
    ("威秀", "零用金-電影"), ("影城", "零用金-電影"), ("劇院", "零用金-電影"),
    # 食材
    ("超市", "零用金-食材"), ("全聯", "零用金-食材"), ("家樂福", "零用金-食材"), ("美廉社", "零用金-食材"),
    # 餐費
    ("統一超商", "零用金-餐費"), ("全家", "零用金-餐費"), ("萊爾富", "零用金-餐費"), ("SEVEN-ELEVEN", "零用金-餐費"),
    ("GS25", "零用金-餐費"), ("麥當勞", "零用金-餐費"), ("餐", "零用金-餐費"), ("飯", "零用金-餐費"), ("麵", "零用金-餐費"),
    ("食堂", "零用金-餐費"), ("素食", "零用金-餐費"), ("煲湯", "零用金-餐費"), ("臭豆腐", "零用金-餐費"),
    ("鹽水雞", "零用金-餐費"), ("酥雞", "零用金-餐費"), ("烤頂雞", "零用金-餐費"), ("葵燒", "零用金-餐費"), ("初月", "零用金-餐費"),
    ("咖啡", "零用金-餐費"), ("CAF", "零用金-餐費"), ("茶", "零用金-餐費"), ("50嵐", "零用金-餐費"), ("路易", "零用金-餐費"),
    ("PAUL", "零用金-餐費"), ("丹麥", "零用金-餐費"), ("蛋糕", "零用金-餐費"), ("餅", "零用金-餐費"), ("桃酥", "零用金-餐費"),
    ("麻油雞", "零用金-餐費"), ("老蘿蔔", "零用金-餐費"), ("聯誼社", "零用金-餐費"), ("美食", "零用金-餐費"),
    ("微風", "零用金-餐費"), ("黑松", "零用金-餐費"), ("金興發", "零用金-餐費"), ("I-MEI", "零用金-餐費"),
    ("goodeggs", "零用金-餐費"), ("SSIYU", "零用金-餐費"), ("Flourish", "零用金-餐費"), ("Dore", "零用金-餐費"),
    ("Local Lo", "零用金-餐費"), ("Redi", "零用金-餐費"), ("Mimi", "零用金-餐費"), ("coco", "零用金-餐費"),
    ("MamaLiLi", "零用金-餐費"), ("LAY BACK", "零用金-餐費"), ("知初", "零用金-餐費"), ("巢屋", "零用金-餐費"),
    ("采豊", "零用金-餐費"), ("一般商品買賣", "零用金-餐費"), ("烘焙", "零用金-餐費"), ("SUKIYA", "零用金-餐費"),
    ("早安", "零用金-餐費"), ("DONG TIANYUE", "零用金-餐費"), ("DAO YAN", "零用金-餐費"), ("ZHI YOU", "零用金-餐費"),
    # 用品（含 AI 訂閱＝個人）
    ("OPENAI", "零用金-用品"), ("CHATGPT", "零用金-用品"), ("ANTHROPIC", "零用金-用品"), ("CLAUDE", "零用金-用品"),
    ("CHATHUB", "零用金-用品"), ("CapCut", "零用金-用品"),
    ("蝦皮", "零用金-用品"), ("SHOPEE", "零用金-用品"), ("MOMO", "零用金-用品"), ("IKEA", "零用金-用品"), ("誠品", "零用金-用品"),
    ("京站", "零用金-用品"), ("巨城", "零用金-用品"), ("寶雅", "零用金-用品"), ("POYA", "零用金-用品"), ("屈臣氏", "零用金-用品"),
    ("文具", "零用金-用品"), ("PCHOME", "零用金-用品"), ("taobao", "零用金-用品"), ("小米", "零用金-用品"),
    ("佳銥", "零用金-用品"), ("巷上", "零用金-用品"), ("特麗樹", "零用金-用品"), ("i color", "零用金-用品"),
    ("ＬＩＮＥ禮物", "零用金-用品"), ("團圓國際", "零用金-用品"), ("百貨", "零用金-用品"), ("特力", "零用金-用品"),
    ("康達盛通", "零用金-用品"), ("曙客", "零用金-用品"), ("DAISO", "零用金-用品"), ("拾元小店", "零用金-用品"),
    # 旅行
    ("飯店", "零用金-旅行"), ("旅館", "零用金-旅行"), ("航空", "零用金-旅行"), ("虎航", "零用金-旅行"), ("客路", "零用金-旅行"),
    ("溫泉", "零用金-旅行"), ("君悅", "零用金-旅行"), ("香格里拉", "零用金-旅行"), ("SUICA", "零用金-旅行"),
    ("Tmoney", "零用金-旅行"), ("esim", "零用金-旅行"),
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
    if any(h in upper for h in TRAVEL_HINTS):
        return "零用金-旅行", "規則：國外消費"
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
        purchases = [c for c in st.purchases if c.amount != 0]
        fee_re = re.compile(r"國外交易(?:服務|手續)費[－-]?\s*([\d.,]+)?")
        decided: list[tuple[Charge, str, str]] = []
        for ch in purchases:
            fm = fee_re.search(ch.description)
            if fm:
                base_amt = int(float(fm.group(1).replace(",", ""))) if fm.group(1) else None
                base = next((d for d in decided if d[0].day == ch.day and d[0].amount == base_amt), None) \
                    or (decided[-1] if decided else None)
                label, reason = (base[1], "跟隨對應消費") if base else ("零用金-旅行", "規則：國外手續費")
            else:
                label, reason = categorize(ch.description, rules)
            decided.append((ch, label, reason))
        for ch, label, reason in decided:
            if label == SKIP_ROW:
                plan.spends.append(SpendAction(f, ch, SKIP_ROW, "不列零用金（只留備註）"))
                continue
            sa = SpendAction(f, ch, label, reason)
            r = find_row(labels, label)
            if r is None:
                sa.reason += f"；細帳沒有「{label}」列 → 改放 {FALLBACK_ROW}"
                sa.row_label = FALLBACK_ROW
                r = find_row(labels, FALLBACK_ROW)
            sa.cell = a1(r, col) if r is not None else ""
            plan.spends.append(sa)
        plan.spends = [x for x in plan.spends if not (x.row_label == SKIP_ROW and x.cell)]
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


def apply_plan(plan: Plan, book, stamp: date, applied: dict, calendar=None, notes_only: bool = False) -> list[str]:
    """寫入：2026細帳 只加備註；含信用卡表加金額＋備註（notes_only=True 時跳過）。回傳改到的格子說明。"""
    detail_title = f"{plan.year}細帳"
    copy_title = f"{plan.year}細帳(含信用卡)"
    detail = book.worksheet(detail_title)
    log: list[str] = []
    if not notes_only:
        copy, created = ensure_copy(book, detail_title, copy_title)
        if created:
            log.append(f"已建立工作表「{copy_title}」")
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
    pending = [] if notes_only else [s for s in plan.spends if s.cell and s.row_label != SKIP_ROW
                                     and s.file.key not in applied]
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
        # 第 25 列「零用金」同額 +，現金餘額不變（照 Jenny 記銀行支出的規則）；只算加進零用金各項的刷卡
        cash_terms = _cash_offsets(pending)
        if cash_terms:
            labels = [r[0] if r else "" for r in formulas]
            cols = month_columns(formulas[0] if formulas else [])
            cash_row = find_row(labels, CASH_ROW)
            card_sum_row = _ensure_summary_rows(copy, formulas, labels, cols, log, copy_title)
            if cash_row is None:
                log.append(f"⚠️ {copy_title} 找不到「{CASH_ROW}」列，沒有加抵銷金額")
            for month, (total, count) in sorted(cash_terms.items()):
                col = cols.get(month)
                if cash_row is None or col is None:
                    continue
                for row, label, note_text_ in ((cash_row, CASH_ROW, f"信用卡消費合計 +{total:,}（{count} 筆；抵銷，現金不變）"),
                                               (card_sum_row, CARD_SUM_ROW, f"信用卡消費合計 +{total:,}（{count} 筆）")):
                    if row is None:
                        continue
                    cell = a1(row, col)
                    formula = formulas[row][col] if row < len(formulas) and col < len(formulas[row]) else ""
                    new = add_term(formula, total)
                    block = f"【信用卡 {month}】{note_text_}\n加註日期：{stamp:%Y-%m-%d}（bank_sync）"
                    existing = notes[row][col] if row < len(notes) and col < len(notes[row]) else ""
                    copy.update(range_name=cell, values=[[new]], value_input_option="USER_ENTERED")
                    copy.update_note(cell, (existing + "\n" + block).strip() if existing else block)
                    log.append(f"{copy_title}!{cell} {label} {formula or '（空白）'} → {new}")
                    if label == CASH_ROW:
                        events.append((f"{copy_title}!{cell}:{stamp}:cash:{month}",
                                       f"【細帳(含信用卡)】{month} {CASH_ROW} +{total:,}（信用卡抵銷）",
                                       f"{copy_title}!{cell}：{formula or '（空白）'} → {new}\n{count} 筆刷卡加進零用金各項，"
                                       f"25 列同額加回，現金餘額不變\n加註日期：{stamp:%Y-%m-%d}"))
    for s in pending:
        applied[s.file.key] = stamp.isoformat()  # 含信用卡表已加過這份帳單

    if calendar:
        for key, title, body in events:
            calendar(key, stamp, title, body)
    return log


CASH_ROW = "零用金"
TOTAL_ROW = "零用金--總支出"
CARD_SUM_ROW = "零用金-信用卡消費"
CASH_SUM_ROW = "零用金-現金消費"


def _cash_offsets(pending: list) -> dict[str, tuple[int, int]]:
    """每個月加進零用金各項的刷卡合計：{月份: (金額, 筆數)}。只算 零用金- 開頭的列（保費支出等不算）。"""
    out: dict[str, list[int]] = {}
    for s in pending:
        if s.row_label.startswith("零用金-"):
            out.setdefault(s.file.statement.ledger_month, []).append(s.charge.amount)
    return {m: (sum(v), len(v)) for m, v in out.items()}


def _ensure_summary_rows(copy, formulas: list, labels: list, cols: dict, log: list, copy_title: str):
    """在含信用卡表加「零用金-信用卡消費」「零用金-現金消費」兩列（第一次才加）。回傳信用卡消費列（0-based）。"""
    existing = find_row(labels, CARD_SUM_ROW)
    if existing is not None:
        return existing
    total_row = find_row(labels, TOTAL_ROW)
    if total_row is None or not cols:
        log.append(f"⚠️ {copy_title} 找不到「{TOTAL_ROW}」列，沒有加統計列")
        return None
    # 放在總支出後面第一個「連續兩列空白」的位置（28 列淨值之後）；找不到就接在最後
    insert_at = next((r for r in range(total_row + 1, min(total_row + 8, len(labels) - 1))
                      if not labels[r] and not labels[r + 1]), len(formulas))
    first, last = min(cols.values()), max(cols.values())
    card_cells = ["" for _ in range(first, last + 1)]
    cash_cells = [f"={a1(0, c)[:-1]}{total_row + 1}-{a1(0, c)[:-1]}{insert_at + 1}" for c in range(first, last + 1)]
    rows = [[CARD_SUM_ROW] + [""] * (first - 1) + card_cells,
            [CASH_SUM_ROW] + [""] * (first - 1) + cash_cells]
    copy.update(range_name=f"A{insert_at + 1}:{a1(0, last)[:-1]}{insert_at + 2}", values=rows,
                value_input_option="USER_ENTERED")
    while len(formulas) < insert_at + 2:
        formulas.append([])
        labels.append("")
    formulas[insert_at], formulas[insert_at + 1] = list(rows[0]), list(rows[1])
    labels[insert_at], labels[insert_at + 1] = CARD_SUM_ROW, CASH_SUM_ROW
    log.append(f"{copy_title} 新增「{CARD_SUM_ROW}」「{CASH_SUM_ROW}」兩列（第 {insert_at + 1}–{insert_at + 2} 列）")
    return insert_at


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


def unclassified_summary(plan: Plan) -> list[tuple[str, int, int]]:
    """對不到規則的消費，依商店名稱歸納：(名稱, 筆數, 金額合計)，金額大到小。"""
    groups: dict[str, list[int]] = {}
    for s in plan.spends:
        if "待分類" not in s.reason:
            continue
        name = re.sub(r"(TAIPEI|Taipei|TAICHU|New Ta|TAINAN)\s*$", "", s.charge.description)
        name = re.sub(r"[A-Z]\d{4}\s*$", "", name)                 # 收單代碼 A9131
        name = re.sub(r"[\(（].*$", "", name).strip()                  # 括號後的分店名
        name = re.sub(r"\d{5,}.*$", "", name).strip()                 # 保單號、期數
        groups.setdefault(name or s.charge.description, []).append(s.charge.amount)
    return sorted(((k, len(v), sum(v)) for k, v in groups.items()), key=lambda x: -abs(x[2]))


def run(year: int, apply: bool = False, banks: tuple = (), notes_only: bool = False, show_unclassified: bool = False) -> Path:
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
    if show_unclassified:
        print("\n待分類的商店（筆數／金額合計）：")
        for name, n, total in unclassified_summary(plan):
            print(f"  {name:<28} {n:>3} 筆 {total:>9,}")
    if not apply:
        print("（只比對，沒有寫入。確認報表後加 --apply 才會寫入總帳。）")
        return report
    calendar = lambda key, day, title, body: print(
        "   行事曆：", title, "→", calendar_add_once(creds, "bank_sync:" + key, day, title, body))
    for line in apply_plan(plan, book, stamp, applied, calendar, notes_only=notes_only):
        print("✓", line)
    save_applied(applied)
    return report
