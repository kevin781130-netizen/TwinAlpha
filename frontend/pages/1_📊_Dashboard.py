"""總覽頁面。"""

from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="總覽", page_icon="📊", layout="wide")

from utils.api_client import health_check, get_rules, run_backtest
from utils.charts import equity_curve_chart, drawdown_chart
from utils.metrics import backtest_metrics
from utils.theme import inject_custom_css, render_metric_row

inject_custom_css()

st.title("📊 總覽")

health = health_check()
if not health.get("ok"):
    st.error("後端離線，請先啟動 `uvicorn app.api.main:app --reload`")
    st.stop()

render_metric_row([
    ("後端狀態", "🟢 運行中", None),
    ("資料庫", "DuckDB + Parquet", None),
    ("市場", "台股 / 美股", None),
    ("版本", "v0.5.0", None),
])

st.divider()
st.subheader("🌏 市場規則對比")

tw = get_rules("TW")
us = get_rules("US")
rules_df = pd.DataFrame([
    {"維度": "交割制度", "台股": f"T+{tw['settlement_days']}", "美股": f"T+{us['settlement_days']}"},
    {"維度": "漲跌幅", "台股": f"±{tw['price_limit_pct']*100:.0f}% (tick 對齊)", "美股": "無限制"},
    {"維度": "交易單位", "台股": f"{tw['lot_size']} 股（可零股）", "美股": f"{us['lot_size']} 股"},
    {"維度": "手續費", "台股": "0.1425% × 折 (最低 20 元)", "美股": "SEC + FINRA"},
    {"維度": "證交稅", "台股": "0.3% (賣出時)", "美股": "無"},
    {"維度": "交易時段", "台股": "09:00 - 13:30", "美股": "09:30 - 16:00 ET"},
])
st.dataframe(rules_df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("🧩 系統模組")

modules = pd.DataFrame([
    {"層級": "市場規則", "模組": "TaiwanRules / USRules", "狀態": "✅ 可用"},
    {"層級": "數據層", "模組": "MarketWarehouse (DuckDB)", "狀態": "✅ 可用"},
    {"層級": "數據層", "模組": "FinMind / yfinance Provider", "狀態": "✅ 可用"},
    {"層級": "因子層", "模組": "SignalDSL", "狀態": "✅ 可用"},
    {"層級": "因子層", "模組": "FactorRegistry", "狀態": "✅ 可用"},
    {"層級": "因子層", "模組": "TWChipsFactorEngine", "狀態": "✅ 可用"},
    {"層級": "因子層", "模組": "USOptionsFactorEngine", "狀態": "✅ 可用"},
    {"層級": "回測層", "模組": "BacktestEngine", "狀態": "✅ 可用"},
    {"層級": "回測層", "模組": "WalkForwardEngine", "狀態": "✅ 可用"},
    {"層級": "Agent 層", "模組": "InvestmentOrchestrator", "狀態": "✅ 可用"},
    {"層級": "風控層", "模組": "RiskGuard", "狀態": "✅ 可用"},
    {"層級": "執行層", "模組": "ShioajiBridge", "狀態": "⚠️ 需 shioaji"},
    {"層級": "審計層", "模組": "VerifiableAuditLog", "狀態": "✅ 可用"},
])
st.dataframe(modules, use_container_width=True, hide_index=True)

st.divider()
st.subheader("🚀 快速回測")

with st.form("quick_backtest"):
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("標的", value="2330")
    with col2:
        start = st.date_input("開始", value=datetime.now() - timedelta(days=730))
    with col3:
        end = st.date_input("結束", value=datetime.now())

    expr = st.text_input("策略表達式", value="ema(close,10)/ema(close,30)-1")
    col1, col2, col3 = st.columns(3)
    with col1:
        upper = st.number_input("上閾值", value=0.02, step=0.005)
    with col2:
        lower = st.number_input("下閾值", value=-0.02, step=0.005)
    with col3:
        submitted = st.form_submit_button("🚀 開始回測", use_container_width=True)

if submitted:
    with st.spinner("回測中..."):
        result = run_backtest(
            symbol=symbol, market="TW",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            expr=expr, upper=upper, lower=lower,
        )
    if "error" in result:
        st.error(result["error"])
    elif "metrics" in result:
        backtest_metrics(result["metrics"])
        st.plotly_chart(equity_curve_chart(result["equity_curve"]), use_container_width=True)
        st.plotly_chart(drawdown_chart(result["equity_curve"]), use_container_width=True)
