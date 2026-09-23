"""回測頁面。"""

from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="回測", page_icon="🔬", layout="wide")

from utils.api_client import run_backtest, run_walk_forward, sweep_parameters, APIError
from utils.charts import equity_curve_chart, returns_histogram, drawdown_chart
from utils.theme import inject_custom_css, render_metric_row

inject_custom_css()

st.title("🔬 回測")

PRESETS = {
    "MA 交叉 (10/30)": ("ema(close, 10) / ema(close, 30) - 1", 0.02, -0.02),
    "MA 交叉 (5/20)": ("ema(close, 5) / ema(close, 20) - 1", 0.01, -0.01),
    "RSI 超買超賣": ("rsi(close, 14) - 50", 20.0, -20.0),
    "布林帶回歸": ("zscore(close, 20)", 1.5, -1.5),
    "20 日動量": ("close / delay(close, 20) - 1", 0.05, -0.05),
}

with st.sidebar:
    st.markdown("### 回測參數")
    symbol = st.text_input("標的代碼", value="2330")
    market = st.selectbox("市場", ["TW", "US"])
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("開始日期", value=datetime.now() - timedelta(days=365 * 3))
    with col2:
        end = st.date_input("結束日期", value=datetime.now())

    st.divider()
    preset = st.selectbox("預設策略", ["自訂"] + list(PRESETS.keys()))
    if preset != "自訂":
        expr, upper, lower = PRESETS[preset]
    else:
        expr = st.text_input("表達式", value="ema(close, 10) / ema(close, 30) - 1")
        upper = st.number_input("上限閾值", value=0.02, format="%.4f")
        lower = st.number_input("下限閾值", value=-0.02, format="%.4f")

    st.divider()
    run_btn = st.button("🚀 執行回測", type="primary", use_container_width=True)
    run_wf = st.checkbox("同時跑 Walk-Forward")
    run_sweep = st.checkbox("同時跑參數掃描")

if run_btn:
    try:
        with st.spinner("回測中..."):
            result = run_backtest(
                symbol=symbol, market=market,
                start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                expr=expr, upper=float(upper), lower=float(lower),
            )
        st.session_state["last_backtest"] = result
        st.session_state["last_backtest_params"] = {
            "symbol": symbol, "market": market,
            "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
            "expr": expr,
        }
    except APIError as e:
        st.error(f"回測失敗：{e}")
        st.stop()

    if run_wf:
        try:
            with st.spinner("Walk-Forward 中..."):
                wf = run_walk_forward(
                    symbol=symbol, market=market,
                    start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                    expr=expr,
                )
            st.session_state["last_wf"] = wf
        except Exception as e:
            st.warning(f"Walk-Forward 失敗：{e}")

    if run_sweep:
        try:
            with st.spinner("參數掃描中..."):
                sweep = sweep_parameters(
                    symbol=symbol, market=market,
                    start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                    fast_range="5,10,15,20,25,30", slow_range="20,30,40,50,60",
                )
            st.session_state["last_sweep"] = sweep
        except Exception as e:
            st.warning(f"參數掃描失敗：{e}")

result = st.session_state.get("last_backtest")
if not result:
    st.info("👈 左側設定參數後，點擊「執行回測」")
    st.stop()

params = st.session_state.get("last_backtest_params", {})
st.markdown(f"**標的**：`{params.get('symbol')}` ({params.get('market')}) · "
            f"**期間**：{params.get('start')} → {params.get('end')} · "
            f"**表達式**：`{params.get('expr')}`")

st.divider()
metrics = result.get("metrics", {})
st.subheader("📈 績效指標")
render_metric_row([
    ("總報酬", f"{metrics.get('total_return', 0):+.2%}", None),
    ("Sharpe", f"{metrics.get('sharpe', 0):.2f}", None),
    ("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}", None),
    ("交易次數", f"{metrics.get('num_trades', 0)}", None),
])

st.divider()
tab1, tab2, tab3, tab4 = st.tabs(["權益曲線", "回撤", "報酬分佈", "交易明細"])
equity_curve = result.get("equity_curve", [])
with tab1:
    st.plotly_chart(equity_curve_chart(equity_curve), use_container_width=True)
with tab2:
    st.plotly_chart(drawdown_chart(equity_curve), use_container_width=True)
with tab3:
    st.plotly_chart(returns_histogram(equity_curve), use_container_width=True)
with tab4:
    trades = result.get("trades", [])
    if trades:
        df = pd.DataFrame(trades)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("無交易記錄")

wf = st.session_state.get("last_wf")
if wf and "summary" in wf:
    st.divider()
    st.subheader("🔁 Walk-Forward 驗證")
    s = wf["summary"]
    render_metric_row([
        ("窗口數", s.get("num_windows", 0), None),
        ("Sharpe 均值", f"{s.get('sharpe_mean', 0):.2f}", None),
        ("Sharpe 標準差", f"{s.get('sharpe_std', 0):.2f}", None),
        ("OOS 一致性", f"{s.get('oos_consistency', 0):.2f}", None),
    ])
    oos = s.get("oos_consistency", 0)
    if oos < 0.3:
        st.error("⚠️ OOS 一致性極低（< 0.3），不建議上實盤。")
    elif oos < 0.5:
        st.warning("⚠️ OOS 一致性偏低（< 0.5），可能過擬合。")
    elif oos < 1.0:
        st.info("⚪ OOS 一致性中等，需進一步驗證。")
    else:
        st.success("✅ OOS 一致性良好（> 1.0）。")

sweep = st.session_state.get("last_sweep")
if sweep:
    st.divider()
    st.subheader("🔍 參數掃描 Top 20")
    sweep_df = pd.DataFrame(sweep)
    if not sweep_df.empty:
        cols_to_show = [c for c in ["fast", "slow", "sharpe", "total_return", "max_drawdown"] if c in sweep_df.columns]
        st.dataframe(sweep_df[cols_to_show].head(20), use_container_width=True, hide_index=True)
