"""組合優化頁面。"""

from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="組合優化", page_icon="💼", layout="wide")

from utils.api_client import optimize_portfolio, APIError
from utils.charts import portfolio_weights
from utils.theme import inject_custom_css, render_metric_row

inject_custom_css()

st.title("💼 組合優化")

with st.sidebar:
    symbols_input = st.text_area("標的清單（逗號分隔）",
                                  value="2330,2317,2454,2412,2881", height=100)
    market = st.selectbox("市場", ["TW", "US"])
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("開始日期", value=datetime.now() - timedelta(days=365 * 3))
    with col2:
        end = st.date_input("結束日期", value=datetime.now())

    method = st.selectbox(
        "優化方法",
        ["hrp", "risk_budgeting", "max_diversification", "mean_risk"],
        format_func=lambda x: {
            "hrp": "層次風險平價 (HRP)",
            "risk_budgeting": "風險平價",
            "max_diversification": "最大分散化",
            "mean_risk": "均值-風險優化",
        }[x],
    )
    run_btn = st.button("🚀 執行優化", type="primary", use_container_width=True)

if run_btn:
    symbols = ",".join([s.strip() for s in symbols_input.split(",") if s.strip()])
    if not symbols:
        st.warning("請輸入至少 2 個標的")
        st.stop()

    try:
        with st.spinner("優化中..."):
            result = optimize_portfolio(
                symbols=symbols, market=market,
                start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                method=method,
            )
        st.session_state["last_portfolio"] = result
    except APIError as e:
        st.error(f"優化失敗：{e}")
        st.stop()

result = st.session_state.get("last_portfolio")
if not result:
    st.info("👈 左側設定參數，點擊「執行優化」")
    st.stop()

if "error" in result:
    st.error(result["error"])
    st.stop()

metrics = result.get("metrics", {})
st.subheader("📈 組合績效")
render_metric_row([
    ("方法", result.get("method", "-"), None),
    ("Sharpe", f"{metrics.get('sharpe', 0):.2f}", None),
    ("總報酬", f"{metrics.get('total_return', 0):+.2%}", None),
    ("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}", None),
])

st.divider()
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("🥧 權重分配")
    weights = result.get("weights", {})
    if weights:
        st.plotly_chart(portfolio_weights(weights), use_container_width=True)
with col2:
    st.subheader("📋 權重明細")
    if weights:
        weights_df = pd.DataFrame([
            {"標的": k, "權重": f"{v:.2%}"}
            for k, v in sorted(weights.items(), key=lambda x: -x[1])
        ])
        st.dataframe(weights_df, use_container_width=True, hide_index=True)

st.divider()
st.metric("年化波動率", f"{metrics.get('annual_volatility', 0):.2%}")
