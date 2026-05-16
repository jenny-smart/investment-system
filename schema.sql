-- Investment system draft schema.
-- Phase 1 can use SQLite. The same shape can later move to Postgres.

CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    institution_id INTEGER REFERENCES institutions(id),
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'TWD',
    owner TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    UNIQUE(institution_id, name, currency)
);

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    name TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'TWD',
    source_name TEXT,
    source_code TEXT,
    source_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    UNIQUE(name, currency, instrument_type)
);

CREATE TABLE IF NOT EXISTS holding_lots (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    purchase_date DATE,
    units REAL NOT NULL DEFAULT 0,
    unit_cost REAL,
    cost_amount_original REAL,
    cost_amount_twd REAL,
    currency TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    instrument_id INTEGER REFERENCES instruments(id),
    trade_date DATE NOT NULL,
    transaction_type TEXT NOT NULL,
    units REAL,
    price REAL,
    amount_original REAL,
    amount_twd REAL,
    fee_twd REAL DEFAULT 0,
    tax_twd REAL DEFAULT 0,
    currency TEXT NOT NULL,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS income_events (
    id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    instrument_id INTEGER REFERENCES instruments(id),
    income_date DATE NOT NULL,
    income_type TEXT NOT NULL,
    amount_original REAL,
    amount_twd REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'TWD',
    tax_twd REAL DEFAULT 0,
    year INTEGER,
    month INTEGER,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS market_price_snapshots (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    price_date DATE NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    source_name TEXT,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(instrument_id, price_date, source_name)
);

CREATE TABLE IF NOT EXISTS fx_rate_snapshots (
    id INTEGER PRIMARY KEY,
    rate_date DATE NOT NULL,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL DEFAULT 'TWD',
    rate REAL NOT NULL,
    source_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(rate_date, base_currency, quote_currency, source_name)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    account_id INTEGER REFERENCES accounts(id),
    instrument_id INTEGER REFERENCES instruments(id),
    units REAL,
    market_price REAL,
    market_value_original REAL,
    market_value_twd REAL,
    cost_twd REAL,
    unrealized_pnl_twd REAL,
    realized_income_twd REAL,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cash_account_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_month TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    balance_original REAL,
    balance_twd REAL,
    currency TEXT NOT NULL DEFAULT 'TWD',
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    UNIQUE(snapshot_month, account_id)
);

CREATE TABLE IF NOT EXISTS monthly_ledger_entries (
    id INTEGER PRIMARY KEY,
    ledger_year INTEGER NOT NULL,
    ledger_month INTEGER NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    amount_twd REAL NOT NULL,
    entry_kind TEXT NOT NULL,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    source_col INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS insurance_policies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    insurer TEXT,
    start_year INTEGER,
    owner TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS insurance_cashflows (
    id INTEGER PRIMARY KEY,
    policy_id INTEGER NOT NULL REFERENCES insurance_policies(id),
    cashflow_year INTEGER NOT NULL,
    premium_twd REAL DEFAULT 0,
    surrender_value_twd REAL,
    rebate_twd REAL DEFAULT 0,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER
);

CREATE TABLE IF NOT EXISTS private_investments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    investment_type TEXT NOT NULL,
    invested_amount_twd REAL,
    expected_return_rate REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT
);

CREATE TABLE IF NOT EXISTS private_investment_cashflows (
    id INTEGER PRIMARY KEY,
    private_investment_id INTEGER NOT NULL REFERENCES private_investments(id),
    cashflow_date DATE,
    cashflow_year INTEGER,
    cashflow_type TEXT NOT NULL,
    amount_twd REAL NOT NULL,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS loan_accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    counterparty TEXT,
    direction TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'TWD',
    note TEXT
);

CREATE TABLE IF NOT EXISTS loan_events (
    id INTEGER PRIMARY KEY,
    loan_account_id INTEGER NOT NULL REFERENCES loan_accounts(id),
    event_date DATE,
    event_type TEXT NOT NULL,
    amount_twd REAL NOT NULL,
    status TEXT,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS distribution_calendar (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER REFERENCES instruments(id),
    platform_name TEXT,
    expected_day TEXT,
    frequency TEXT,
    currency TEXT,
    source_workbook TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS sheet_sync_logs (
    id INTEGER PRIMARY KEY,
    workbook_id TEXT NOT NULL,
    workbook_name TEXT NOT NULL,
    sheet_name TEXT,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER,
    col_count INTEGER,
    status TEXT NOT NULL,
    message TEXT
);

CREATE VIEW IF NOT EXISTS monthly_income_summary AS
SELECT
    year,
    month,
    income_type,
    SUM(amount_twd) AS amount_twd
FROM income_events
GROUP BY year, month, income_type;

CREATE VIEW IF NOT EXISTS latest_portfolio_snapshot AS
SELECT ps.*
FROM portfolio_snapshots ps
JOIN (
    SELECT
        COALESCE(account_id, -1) AS account_key,
        COALESCE(instrument_id, -1) AS instrument_key,
        MAX(snapshot_date) AS max_snapshot_date
    FROM portfolio_snapshots
    GROUP BY COALESCE(account_id, -1), COALESCE(instrument_id, -1)
) latest
    ON COALESCE(ps.account_id, -1) = latest.account_key
    AND COALESCE(ps.instrument_id, -1) = latest.instrument_key
    AND ps.snapshot_date = latest.max_snapshot_date;
