"""TW/US Invest OS — Streamlit 前端主入口。"""

import streamlit as st

st.set_page_config(
    page_title="TW/US Invest OS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.api_client import health_check
from utils.theme import inject_custom_css

inject_custom_css()


def render_sidebar():
    with st.sidebar:
        st.markdown("### 📈 TW/US Invest OS")
        st.caption("台股 / 美股量化研究框架")
        st.divider()

        health = health_check()
        if health.get("ok"):
            st.success("✅ 後端已連線", icon="🟢")
        else:
            st.error("❌ 後端離線", icon="🔴")
            st.caption("請啟動：`uvicorn app.api.main:app`")
            if health.get("error"):
                st.caption(f"錯誤：{health['error'][:80]}")

        st.divider()
        st.markdown("##### 快速導航")
        st.page_link("pages/1_📊_Dashboard.py", label="總覽", icon="📊")
        st.page_link("pages/2_🔬_Backtest.py", label="回測", icon="🔬")
        st.page_link("pages/3_📈_Data_Explorer.py", label="數據探索", icon="📈")
        st.page_link("pages/4_🤖_Agent_Analysis.py", label="Agent 分析", icon="🤖")
        st.page_link("pages/5_💼_Portfolio.py", label="組合優化", icon="💼")
        st.page_link("pages/6_🛡️_Risk.py", label="風控", icon="🛡️")
        st.page_link("pages/7_📡_Paper_Trading.py", label="模擬盤", icon="📡")
        st.page_link("pages/8_🔐_Audit.py", label="審計日誌", icon="🔐")

        st.divider()
        st.caption("v0.5.0 · MIT License")
        st.caption("研究框架，非實盤系統")


def render_home():
    st.title("📈 TW/US Invest OS")
    st.markdown("##### 台股 / 美股量化研究框架")

    st.warning(
        "⚠️ **定位聲明**：本框架是研究工具，不是實盤交易系統。"
        "賺錢取決於你的策略，不取決於模組數量。"
    )

    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("支援市場", "台股 / 美股")
    col2.metric("內置因子", "450+")
    col3.metric("回測引擎", "3 種")
    col4.metric("煙霧測試", "17 項")

    st.divider()

    st.markdown("### 🚀 快速開始")
    st.markdown("""
    **第一次使用？按以下順序操作：**

    1. **啟動後端** — `uvicorn app.api.main:app --reload`
    2. **灌入數據** — `python scripts/ingest_real_data.py --market TW --symbols 2330`
    3. **跑第一次回測** — 左側選單點「回測」
    4. **驗證因子** — 左側選單點「數據探索」
    5. **跑模擬盤** — `python scripts/tw_paper_trading.py --dry-run`
    """)

    st.divider()

    st.markdown("### 📚 核心能力")
    cols = st.columns(3)
    with cols[0]:
        st.markdown("""
        **數據層**
        - DuckDB + Parquet 本地倉庫
        - FinMind 台股 / yfinance 美股
        - 三大法人籌碼 / 期權鏈
        """)
    with cols[1]:
        st.markdown("""
        **分析層**
        - DSL 信號引擎
        - 450+ 內置因子（Alpha101/158/191）
        - IC / 分層 / 衰減診斷
        """)
    with cols[2]:
        st.markdown("""
        **決策層**
        - 多分析師 + 多空辯論
        - 事件驅動決策
        - 三層風控
        """)


def main():
    render_sidebar()
    render_home()


if __name__ == "__main__":
    main()
