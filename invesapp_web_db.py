from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any
import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False

APP_VERSION = "web-db-v1"
DB_PATH = Path(__file__).resolve().parent / "investment_web.db"
PLATFORMS = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES = ["TWD", "USD", "CNY", "JPY", "ZAR"]
FX_PAIRS = {"TWD": None, "USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}

TW_PRESETS = {
    "儒鴻":"1476.TW", "大魯閣":"1432.TW", "中砂":"1560.TW", "中鴻":"2014.TW", "凱美":"2375.TW",
    "華碩":"2357.TW", "日勝生":"2547.TW", "晶華":"2707.TW", "中壽":"2823.TW", "凱基金":"2883.TW",
    "凱基金乙特":"2883B.TW", "聯陽":"3014.TW", "景碩":"3189.TW", "緯創":"3231.TW", "東隆興":"4401.TWO",
    "和碩":"4938.TW", "松翰":"5471.TWO", "智冠":"5478.TWO", "久元":"6261.TWO", "台塑化":"6505.TW",
    "上銀":"2049.TW", "元大高股息":"0056.TW", "元大台灣50":"0050.TW", "泰碩":"3338.TW", "尼得科超眾":"6230.TW",
    "立積":"4968.TW", "鈺齊-KY":"9802.TW", "東陽":"1319.TW", "華邦電":"2344.TW", "元大金":"2885.TW",
    "鴻海":"2317.TW", "長榮":"2603.TW", "長華*":"8070.TW", "群創":"3481.TW", "集盛":"1455.TW",
    "華新":"1605.TW", "第一銅":"2009.TW", "大聯大":"3702.TW", "富邦特選高股息30":"00900.TW",
    "群益台灣精選高息":"00919.TW", "富邦全球投等債":"00740B.TW", "群益半導體收益":"00927.TW",
    "華泰":"2329.TW", "圓剛":"2417.TW", "楠梓電":"2316.TW", "富邦台50":"006208.TW", "南亞科":"2408.TW",
    "欣興":"3037.TW", "京元電子":"2449.TW", "國巨":"2327.TW"
}
FUND_PRESETS = {
    "acft94":  ("富蘭克林華美新興國家固定收益B-新臺幣", "yp010000", "TWD", "基富通"),
    "acai222": ("柏瑞新興邊境非投資等級債券基金-B類型", "yp010000", "TWD", "基富通"),
    "acft99":  ("富蘭克林華美新興國家固定收益B-人民幣", "yp010000", "CNY", "基富通"),
    "shzx0":   ("貝萊德全球智慧數據股票入息Hedged A6日圓", "yp010001", "JPY", "基富通"),
    "TLZO3":   ("安聯收益成長AMgi月收總收益（日圓避險）", "yp010001", "JPY", "基富通"),
    "acob36":  ("大華銀新加坡房地產收益基金-美元月配", "yp010000", "USD", "渣打基金"),
    "pizn8":   ("東方匯理新興市場債券A美元（月配）", "yp010001", "USD", "渣打基金"),
    "pizo1":   ("東方匯理新興市場債券U美元（月配）", "yp010001", "USD", "渣打基金"),
    "anzb6":   ("高盛新興市場債券基金Y股美元", "yp010001", "USD", "渣打基金"),
    "pizm9":   ("東方匯理新興市場債券U南非幣（月配）", "yp010001", "ZAR", "台新基金"),
    "ANZH2":   ("高盛新興市場債券基金Y南非幣對沖（月配）", "yp010001", "ZAR", "台新基金"),
}

st.set_page_config(page_title="Jenny 投資即時市值系統", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st.markdown('''<style>
.stApp{background:#f7faf9;color:#0f2b20}.block-container{padding-top:.6rem;max-width:1600px}
.fixed{position:sticky;top:0;z-index:999;background:#f7faf9;padding:8px 0 12px;border-bottom:1px solid #e4ece8}
.hero{background:white;border:1px solid #e5eae8;border-radius:16px;padding:16px 20px;box-shadow:0 1px 6px rgba(0,0,0,.05)}
[data-testid="stMetric"],[data-testid="stDataFrame"]{background:white!important;border:1px solid #e5eae8!important;border-radius:14px!important;box-shadow:0 1px 4px rgba(0,0,0,.04)!important}
.stButton>button{background:#10b981!important;color:white!important;border:0!important;border-radius:10px!important;font-weight:700!important}
.pill{display:inline-block;background:#ecfdf5;color:#047857;border:1px solid #bbf7d0;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;margin-right:6px}
</style>''', unsafe_allow_html=True)

def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            name TEXT NOT NULL,
            ticker TEXT DEFAULT '',
            fund_code TEXT DEFAULT '',
            fund_pattern TEXT DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'TWD',
            units REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0,
            monthly_dividend_per_unit REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.commit()
    return c
def load_positions():
    return pd.read_sql_query("SELECT * FROM positions ORDER BY platform,id", conn())

def add_position(row):
    c = conn()
    try:
        c.execute("""INSERT INTO positions(platform,asset_type,name,ticker,fund_code,fund_pattern,currency,units,avg_cost,monthly_dividend_per_unit,note)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
            row["platform"], row["asset_type"], row["name"], row.get("ticker", ""),
            row.get("fund_code", ""), row.get("fund_pattern", ""), row["currency"],
            float(row.get("units", 0) or 0), float(row.get("avg_cost", 0) or 0),
            float(row.get("monthly_dividend_per_unit", 0) or 0), row.get("note", "")
        ))
        c.commit()
    finally:
        c.close()
def update_positions(df):
    c=conn()
    for _,r in df.iterrows():
        c.execute('''UPDATE positions SET platform=?,asset_type=?,name=?,ticker=?,fund_code=?,fund_pattern=?,currency=?,units=?,avg_cost=?,monthly_dividend_per_unit=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (r.platform,r.asset_type,r.name,r.ticker,r.fund_code,r.fund_pattern,r.currency,float(r.units or 0),float(r.avg_cost or 0),float(r.monthly_dividend_per_unit or 0),r.note,int(r.id)))
    c.commit()

def delete_position(pid:int):
    conn().execute("DELETE FROM positions WHERE id=?",(pid,)); conn().commit()

def seed():
    if not load_positions().empty: return
    for name,ticker in TW_PRESETS.items(): add_position(dict(platform="台股",asset_type="台股",name=name,ticker=ticker,fund_code="",fund_pattern="",currency="TWD",units=0,avg_cost=0,monthly_dividend_per_unit=0,note="預設"))
    for t,n in [("PYPL","PayPal"),("XYZ","Block / XYZ")]: add_position(dict(platform="美股",asset_type="美股",name=n,ticker=t,fund_code="",fund_pattern="",currency="USD",units=0,avg_cost=0,monthly_dividend_per_unit=0,note="預設"))
    for code,(name,pat,cur,plat) in FUND_PRESETS.items(): add_position(dict(platform=plat,asset_type="基金",name=name,ticker="",fund_code=code,fund_pattern=pat,currency=cur,units=0,avg_cost=0,monthly_dividend_per_unit=0,note="預設"))

def fnum(v:Any):
    try:
        if v is None or pd.isna(v): return None
        if isinstance(v,str):
            s=v.replace(',','').replace('$','').strip()
            if s in ('','-','—'): return None
            return float(s)
        return float(v)
    except Exception: return None

def money(v,dec=0):
    n=fnum(v); return '-' if n is None else f"{n:,.{dec}f}"
def smoney(v):
    n=fnum(v); return '-' if n is None else f"{n:+,.0f}"
def pct(v):
    n=fnum(v); return '-' if n is None else f"{n:.2%}"

@st.cache_data(ttl=300,show_spinner=False)
def yahoo_price(ticker):
    if not ticker: return None,'無代碼'
    if not HAS_YF: return None,'缺少 yfinance'
    try:
        t=yf.Ticker(ticker); p=getattr(t.fast_info,'last_price',None)
        if p is None:
            h=t.history(period='5d')
            if not h.empty: p=h['Close'].dropna().iloc[-1]
        return (float(p),'ok') if p is not None else (None,'無價格')
    except Exception as e: return None,str(e)[:50]
@st.cache_data(ttl=300,show_spinner=False)
def fund_nav(code,pattern):
    if not code or not pattern: return None,'無基金代碼'
    if not HAS_BS4: return None,'缺少 beautifulsoup4'
    try:
        url=f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
        r=requests.get(url,timeout=20,headers={'User-Agent':'Mozilla/5.0'}); r.raise_for_status()
        soup=BeautifulSoup(r.text,'lxml'); table=soup.select_one('#article form table')
        if table:
            rows=table.find_all('tr')
            if len(rows)>=2:
                cells=rows[1].find_all('td')
                if len(cells)>=2: return float(cells[1].get_text(strip=True).replace(',','')),'ok'
        return None,'找不到淨值'
    except Exception as e: return None,str(e)[:50]
@st.cache_data(ttl=300,show_spinner=False)
def fx(cur):
    if cur=='TWD': return 1.0,'ok'
    pair=FX_PAIRS.get(cur)
    if not pair: return None,'未知幣別'
    return yahoo_price(pair)

def enrich(df):
    rows=[]
    for _,r in df.iterrows():
        cur=r.currency or 'TWD'; units=float(r.units or 0); cost=float(r.avg_cost or 0)
        price,status = yahoo_price(r.ticker) if r.asset_type in ['台股','美股'] else fund_nav(r.fund_code,r.fund_pattern)
        rate,fxs=fx(cur); orig_cost=units*cost
        orig_value=units*price if price is not None else None
        twd_cost=orig_cost*rate if rate is not None else None
        twd_value=orig_value*rate if orig_value is not None and rate is not None else None
        pnl=twd_value-twd_cost if twd_value is not None and twd_cost is not None else None
        div=units*float(r.monthly_dividend_per_unit or 0)*(rate or 0)
        d=r.to_dict(); d.update({'即時價格/淨值':price,'匯率':rate,'台幣成本':twd_cost,'台幣市值':twd_value,'損益':pnl,'損益率':pnl/twd_cost if pnl is not None and twd_cost else None,'每月配息':div,'狀態':'✓' if status=='ok' and fxs=='ok' else f'價:{status} 匯:{fxs}'})
        rows.append(d)
    return pd.DataFrame(rows)

def display(df):
    out=df.copy()
    for c in ['即時價格/淨值','匯率']:
        if c in out: out[c]=out[c].apply(lambda x: money(x,4))
    for c in ['台幣成本','台幣市值','損益','每月配息']:
        if c in out: out[c]=out[c].apply(money)
    if '損益率' in out: out['損益率']=out['損益率'].apply(pct)
    return out

seed(); positions=load_positions(); enriched=enrich(positions)
val=enriched['台幣市值'].dropna().sum() if not enriched.empty else 0
cost=enriched['台幣成本'].dropna().sum() if not enriched.empty else 0
pnl=enriched['損益'].dropna().sum() if not enriched.empty else 0
div=enriched['每月配息'].dropna().sum() if not enriched.empty else 0
with st.container():
    st.markdown('<div class="fixed"><div class="hero">', unsafe_allow_html=True)
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric('總台幣市值', money(val), delta=f'{smoney(pnl)} / {pct(pnl/cost if cost else None)}')
    c2.metric('總台幣成本', money(cost)); c3.metric('每月配息', money(div)); c4.metric('投資筆數', f'{len(positions):,}')
    if c5.button('🔄 更新即時價'): st.cache_data.clear(); st.rerun()
    st.markdown('<span class="pill">台股</span><span class="pill">美股</span><span class="pill">基富通</span><span class="pill">渣打基金</span><span class="pill">台新基金</span><span class="pill">匯率</span>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

tabs=st.tabs(['總覽','台股','美股','基富通','渣打基金','台新基金','匯率','新增 / 編輯'])
show=['platform','asset_type','name','ticker','fund_code','currency','units','avg_cost','即時價格/淨值','匯率','台幣成本','台幣市值','損益','損益率','每月配息','狀態']
with tabs[0]:
    st.subheader('資產配置')
    if not enriched.empty:
        s=enriched.groupby('platform').agg(台幣成本=('台幣成本','sum'),台幣市值=('台幣市值','sum'),損益=('損益','sum'),每月配息=('每月配息','sum'),筆數=('id','count')).reset_index()
        s['損益率']=s.apply(lambda r:r['損益']/r['台幣成本'] if r['台幣成本'] else None,axis=1)
        a,b=st.columns([1,1.7]); a.bar_chart(s.set_index('platform')[['台幣市值']],height=330); b.dataframe(display(s),use_container_width=True,hide_index=True,height=330)
    st.subheader('全部投資產品')
    st.dataframe(display(enriched[show]),use_container_width=True,hide_index=True,height=520)
for i,p in enumerate(PLATFORMS,1):
    with tabs[i]:
        st.subheader(p); v=enriched[enriched.platform==p].copy()
        if v.empty: st.info(f'尚無 {p} 資料')
        else:
            m1,m2,m3,m4=st.columns(4); m1.metric('台幣市值',money(v['台幣市值'].sum())); m2.metric('台幣成本',money(v['台幣成本'].sum())); m3.metric('損益',smoney(v['損益'].sum())); m4.metric('每月配息',money(v['每月配息'].sum()))
            st.dataframe(display(v[show]),use_container_width=True,hide_index=True,height=620)
with tabs[6]:
    fxrows=[]
    for cur in CURRENCIES:
        r,s=fx(cur); fxrows.append({'幣別':cur,'對台幣匯率':money(r,4),'狀態':'✓' if s=='ok' else f'⚠ {s}'})
    st.dataframe(pd.DataFrame(fxrows),use_container_width=True,hide_index=True)
with tabs[7]:
    st.subheader('新增投資產品')
    with st.form('add',clear_on_submit=True):
        c1,c2,c3=st.columns(3); platform=c1.selectbox('平台',PLATFORMS); asset_type=c2.selectbox('類型',ASSET_TYPES); currency=c3.selectbox('幣別',CURRENCIES)
        name=st.text_input('產品名稱')
        c4,c5,c6=st.columns(3); ticker=c4.text_input('股票 Yahoo 代碼'); fund_code=c5.text_input('基金 MoneyDJ 代號'); fund_pattern=c6.text_input('基金 pattern')
        c7,c8,c9=st.columns(3); units=c7.number_input('單位數 / 股數',0.0,step=1.0); avg_cost=c8.number_input('平均成本（原幣）',0.0,step=.01); md=c9.number_input('每單位月配息（原幣）',0.0,step=.0001,format='%.4f')
        note=st.text_input('備註')
        if st.form_submit_button('新增'):
            if not name: st.error('請輸入產品名稱')
            else: add_position(dict(platform=platform,asset_type=asset_type,name=name,ticker=ticker,fund_code=fund_code,fund_pattern=fund_pattern,currency=currency,units=units,avg_cost=avg_cost,monthly_dividend_per_unit=md,note=note)); st.success('已新增'); st.rerun()
    st.subheader('批次編輯')
    cols=['id','platform','asset_type','name','ticker','fund_code','fund_pattern','currency','units','avg_cost','monthly_dividend_per_unit','note']
    edited=st.data_editor(positions[cols],use_container_width=True,hide_index=True,height=520,num_rows='fixed',column_config={'platform':st.column_config.SelectboxColumn('平台',options=PLATFORMS),'asset_type':st.column_config.SelectboxColumn('類型',options=ASSET_TYPES),'currency':st.column_config.SelectboxColumn('幣別',options=CURRENCIES),'id':st.column_config.NumberColumn('ID',disabled=True)},key='editor')
    c10,c11=st.columns([1,3])
    if c10.button('💾 儲存編輯'): update_positions(edited); st.success('已儲存'); st.rerun()
    pid=c11.number_input('刪除 ID',0,step=1)
    if st.button('🗑️ 刪除指定 ID') and pid: delete_position(int(pid)); st.success(f'已刪除 ID {pid}'); st.rerun()
