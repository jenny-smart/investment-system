}


def gas_fund_code_candidates(code: Any) -> list[str]:
    raw = normalize_text(code)
    if not raw:
        return []
    candidates = [raw]
    for preset_code in FUND_PRESETS:
        if preset_code.lower() == raw.lower():
            candidates.append(preset_code)
            break
    candidates.extend([raw.upper(), raw.lower()])
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped

INVESTMENT_ITEMS_DUPLICATE = [
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'CNY', '基金', '富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣', '', 'acft99', 'yp010000'),
    ('基富通', 'CNY', '基金', '富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣', '', 'acft99', 'yp010000'),
    ('基富通', 'JPY', '基金', '貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息', '', 'shzx0', 'yp010001'),
    ('基富通', 'JPY', '基金', '貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息', '', 'shzx0', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'XYZ', 'XYZ', '', ''),
    ('渣打基金', 'USD', '基金', '大華銀新加坡房地產收益基金-美元月配(後收)', '', 'acob36', 'yp010000'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'ZAR', '基金', '東方匯理基金新興市場債券U 南非幣(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'USD', '基金', '高盛新興市場債券基金Y股美元', '', 'anzb6', 'yp010001'),
    ('台新基金', 'USD', '基金', '東方匯理基金新興市場債券U 美元(穩定月配息)', '', 'pizo1', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
]

st.set_page_config(
    page_title="Jenny 投資系統",
    page_icon="📈",
    layout="wide"
)

# ── CSS：保留雲端工具列空間，避免標題被 Streamlit Cloud header 蓋住 ───────
st.markdown("""
<style>
.stApp { background:#f8fafc; color:#1e293b; }
.block-container { padding-top:4.75rem; max-width:1600px; }
.app-page-title {
    display: block !important;
    position: relative !important;
    z-index: 1 !important;
    margin: 0 0 0.6rem 0 !important;
    color: #1e293b !important;
    font-size: 30px !important;
    line-height: 1.25 !important;
    font-weight: 800 !important;
    letter-spacing: 0 !important;
}
@media (max-width: 640px) {
    .block-container { padding-top:5.25rem; }
    .app-page-title { font-size: 24px !important; }
}
.hero { position:relative; z-index:0; background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:16px 20px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
[data-testid="stMetric"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:12px !important; padding:16px 18px !important; box-shadow:0 1px 4px rgba(0,0,0,.05) !important; }
[data-testid="stMetricValue"] { font-size:1.35rem !important; font-weight:700 !important; }
[data-testid="stDataFrame"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:10px !important; }
.stButton > button { background:#10b981 !important; color:#fff !important; border-radius:10px !important; border:0 !important; font-weight:600 !important; }
.stButton > button:hover { background:#059669 !important; }
.stTabs [data-baseweb="tab"] { font-size:13px !important; font-weight:500 !important; color:#64748b !important; }
.stTabs [aria-selected="true"] { color:#10b981 !important; font-weight:700 !important; border-bottom-color:#10b981 !important; }
.stAlert { border-radius:10px !important; }
/* ── Tab 質感升級 ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #f1f5f9;
    padding: 6px 8px;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    height: 36px;
    padding: 0 16px;
    border-radius: 8px;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #64748b !important;
    background: transparent;
    border: none;
    white-space: nowrap;
}
.stTabs [data-baseweb="tab"]:hover {
    background: #e2e8f0 !important;
    color: #334155 !important;
}
.stTabs [aria-selected="true"] {
    background: #fff !important;
    color: #10b981 !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    display: none;
}
.stTabs [data-baseweb="tab-border"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)


_original_st_dataframe = st.dataframe


def _localized_number_config(config: Any) -> Any:
    if not isinstance(config, dict):
        return config
    out = dict(config)
    type_config = out.get("type_config")
    if isinstance(type_config, dict) and type_config.get("type") == "number":
        new_type_config = dict(type_config)
        new_type_config["format"] = "localized"
        out["type_config"] = new_type_config
    return out


def _dataframe_with_localized_numbers(data: Any = None, *args: Any, **kwargs: Any) -> Any:
    df = getattr(data, "data", data)
    if isinstance(df, pd.DataFrame):
        column_config = dict(kwargs.get("column_config") or {})
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                existing = column_config.get(col)
                column_config[col] = (
                    st.column_config.NumberColumn(str(col), format="localized")
                    if existing is None
                    else _localized_number_config(existing)
                )
        if column_config:
            kwargs["column_config"] = column_config
    return _original_st_dataframe(data, *args, **kwargs)


st.dataframe = _dataframe_with_localized_numbers


# ════════════════════════════════════════════════════════════════════════════
# 以下所有函式與原版完全相同，未做任何更動
# ════════════════════════════════════════════════════════════════════════════

def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.environ.get(name, default)


@st.cache_resource(show_spinner=False)
def supabase_client() -> Client:
    url = get_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    key = get_secret("SUPABASE_ANON_KEY", "")
    if not key:
        st.error("缺少 SUPABASE_ANON_KEY")
        st.stop()
    return create_client(url, key)


def normalize_number(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or pd.isna(v):
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
            if v in {"", "-", "—", "nan", "None"}:
                return default
        return float(v)
    except Exception:
        return default


def normalize_text(v: Any, default: str = "") -> str:
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    return str(v).strip()


def normalize_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except Exception:
