"""資料安全頁：匯出、預設清單、Supabase 欄位提醒 SQL。"""
from __future__ import annotations


import streamlit as st
from invest_app.core import (
    ensure_columns,
    load_positions,
    right_align_numbers,
)
from invest_app.positions_admin import (
    seed_presets,
)


def render_data_safety_page(positions) -> None:
        st.subheader("資料安全")
        with st.expander("資料庫欄位提醒：請確認 Supabase 欄位"):
            st.code("""
    alter table portfolio_snapshots add column if not exists bank_total numeric;
    alter table portfolio_snapshots add column if not exists insurance_total numeric;
    alter table portfolio_snapshots add column if not exists huaisi_total numeric;
    alter table portfolio_snapshots add column if not exists uncle_total numeric;
    alter table portfolio_snapshots add column if not exists fx_cash_total numeric;
    alter table portfolio_snapshots add column if not exists deposits_total numeric;
    alter table portfolio_snapshots add column if not exists other_assets_total numeric;
    alter table portfolio_snapshots add column if not exists grand_total numeric;
    alter table latest_portfolio_values add column if not exists bank_total numeric;
    alter table latest_portfolio_values add column if not exists insurance_total numeric;
    alter table latest_portfolio_values add column if not exists huaisi_total numeric;
    alter table latest_portfolio_values add column if not exists uncle_total numeric;
    alter table latest_portfolio_values add column if not exists fx_cash_total numeric;
    alter table latest_portfolio_values add column if not exists deposits_total numeric;
    alter table latest_portfolio_values add column if not exists other_assets_total numeric;
    alter table latest_portfolio_values add column if not exists grand_total numeric;
    alter table positions add column if not exists purchase_ym text default '';
    alter table positions add column if not exists dividend_received_original_total numeric default 0;
    alter table positions add column if not exists dividend_received_original_base numeric default 0;
    alter table positions add column if not exists dividend_received_total numeric default 0;
    alter table positions add column if not exists dividend_note text default '';
    alter table positions add column if not exists dividend_pay_date text default '';
    alter table positions add column if not exists is_reinvest boolean default false;

    alter table fund_dividends add column if not exists fund_name text default '';
    alter table fund_dividends add column if not exists actual_div_amount numeric default 0;
    alter table dividend_log add column if not exists fund_name text default '';
    alter table dividend_log add column if not exists actual_div_amount numeric default 0;

    create table if not exists stock_dividend_log (
        id bigserial primary key,
        platform text default '台股',
        ticker text default '',
        name text default '',
        currency text default 'TWD',
        ex_date text default '',
        cash_pay_date text default '',
        stock_pay_date text default '',
        shares_at_ex numeric default 0,
        cash_dividend_per_share numeric default 0,
        estimated_cash_total numeric default 0,
        actual_cash_total numeric default 0,
        stock_dividend_per_share numeric default 0,
        estimated_stock_shares numeric default 0,
        actual_stock_shares numeric default 0,
        is_cash_received boolean default false,
        is_stock_received boolean default false,
        source text default '',
        note text default '',
        created_at timestamptz default now()
    );
    alter table stock_dividend_log add column if not exists platform text default '台股';
    alter table stock_dividend_log add column if not exists ticker text default '';
    alter table stock_dividend_log add column if not exists name text default '';
    alter table stock_dividend_log add column if not exists currency text default 'TWD';
    alter table stock_dividend_log add column if not exists ex_date text default '';
    alter table stock_dividend_log add column if not exists cash_pay_date text default '';
    alter table stock_dividend_log add column if not exists stock_pay_date text default '';
    alter table stock_dividend_log add column if not exists shares_at_ex numeric default 0;
    alter table stock_dividend_log add column if not exists cash_dividend_per_share numeric default 0;
    alter table stock_dividend_log add column if not exists estimated_cash_total numeric default 0;
    alter table stock_dividend_log add column if not exists actual_cash_total numeric default 0;
    alter table stock_dividend_log add column if not exists stock_dividend_per_share numeric default 0;
    alter table stock_dividend_log add column if not exists estimated_stock_shares numeric default 0;
    alter table stock_dividend_log add column if not exists actual_stock_shares numeric default 0;
    alter table stock_dividend_log add column if not exists is_cash_received boolean default false;
    alter table stock_dividend_log add column if not exists is_stock_received boolean default false;
    alter table stock_dividend_log add column if not exists source text default '';
    alter table stock_dividend_log add column if not exists note text default '';
    alter table stock_dividend_log add column if not exists created_at timestamptz default now();


    """, language="sql")
        st.error("安全版 v7：不會自動建立預設資料，也不會自動清空資料。")
        st.markdown("#### 目前 Supabase 資料匯出")
        if positions.empty:
            st.warning("目前 positions 是空的。")
        else:
            export_df = ensure_columns(positions).sort_values(["sort_order", "id"], na_position="last")
            st.download_button("⬇️ 下載目前 Supabase positions 備份 CSV", data=export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_update.csv", mime="text/csv", key="download_positions_backup_safe")
            st.dataframe(right_align_numbers(export_df.head(100)), use_container_width=True, hide_index=True)
        st.markdown("#### 手動建立預設清單")
        st.caption("只有在 positions 完全空白，而且你確定要重建預設清單時才按。")
        confirm_seed = st.checkbox("我確認 positions 是空的，且我要建立預設清單", key="confirm_manual_seed")
        if st.button("手動建立預設清單", key="manual_seed_button", disabled=not confirm_seed):
            latest = load_positions()
            if not latest.empty:
                st.error("positions 不是空的，已取消建立。")
            else:
                seed_presets(); st.success("已手動建立預設清單。"); st.rerun()
