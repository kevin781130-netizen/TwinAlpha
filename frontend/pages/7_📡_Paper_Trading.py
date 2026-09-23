"""模擬盤監控頁面。"""

import json
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="模擬盤監控", page_icon="📡", layout="wide")

from utils.theme import inject_custom_css, render_metric_row

inject_custom_css()

st.title("📡 模擬盤監控")

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "data_lake" / "paper_trading_state.json"
TRADES_PATH = ROOT / "data_lake" / "paper_trading_trades.jsonl"

st.info(
    "💡 **啟動模擬盤**：在終端機執行\n"
    "```bash\n"
    "python scripts/tw_paper_trading.py --symbols 2330 --dry-run\n"
    "```"
)

auto_refresh = st.checkbox("🔄 自動刷新（每 30 秒）", value=False)
if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=30_000, key="paper_refresh")
    except ImportError:
        st.warning("需安裝 `streamlit-autorefresh`")

if not STATE_PATH.exists():
    st.warning(f"找不到狀態檔案：{STATE_PATH}")
    st.caption("請先啟動 `python scripts/tw_paper_trading.py`")
    st.stop()

try:
    with open(STATE_PATH) as f:
        state = json.load(f)
except Exception as e:
    st.error(f"讀取狀態失敗：{e}")
    st.stop()

st.markdown(f"**最後更新**：{state.get('saved_at', 'N/A')}")
st.divider()

positions = state.get("positions", {})
trades_today = state.get("trades_today", [])
daily_pnl = state.get("daily_pnl", 0)
daily_trades = state.get("daily_trade_count", 0)

render_metric_row([
    ("持倉數", len(positions), None),
    ("今日交易", daily_trades, None),
    ("當日盈虧", f"{daily_pnl:+,.0f}", None),
    ("風控狀態", "🚨 熔斷中" if state.get("circuit_breaker_active") else "✅ 正常", None),
])

st.divider()
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("💼 當前持倉")
    if positions:
        pos_df = pd.DataFrame([
            {"標的": k, "數量": v.get("qty", 0), "平均成本": f"{v.get('avg_cost', 0):.2f}"}
            for k, v in positions.items()
        ])
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("無持倉")

with col2:
    st.subheader("📊 分佈")
    if positions:
        import plotly.graph_objects as go
        labels = list(positions.keys())
        values = [v.get("qty", 0) * v.get("avg_cost", 0) for v in positions.values()]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.5,
                                      textinfo="label+percent")])
        fig.update_layout(template="plotly_dark", height=300, showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("無數據")

st.divider()
st.subheader("📝 今日交易")
if trades_today:
    trades_df = pd.DataFrame(trades_today)
    if "timestamp" in trades_df.columns:
        trades_df["timestamp"] = pd.to_datetime(trades_df["timestamp"]).dt.strftime("%H:%M:%S")
    cols_to_show = [c for c in ["timestamp", "symbol", "side", "qty", "price", "status"]
                    if c in trades_df.columns]
    st.dataframe(trades_df[cols_to_show].iloc[::-1], use_container_width=True, hide_index=True)
else:
    st.info("今日無交易")

st.divider()
st.subheader("📚 歷史交易記錄")
if TRADES_PATH.exists():
    try:
        with open(TRADES_PATH) as f:
            all_trades = [json.loads(line) for line in f if line.strip()]
        if all_trades:
            all_df = pd.DataFrame(all_trades)
            st.caption(f"共 {len(all_df)} 筆記錄")
            st.dataframe(all_df.tail(50).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("無歷史記錄")
    except Exception as e:
        st.error(f"讀取失敗：{e}")
