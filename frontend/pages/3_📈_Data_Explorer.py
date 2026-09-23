"""數據探索頁面。"""

from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="數據探索", page_icon="📈", layout="wide")

from utils.api_client import (
    tw_chips, us_options, qweave_batch, inspect_factor, validate_factor, APIError,
)
from utils.theme import inject_custom_css

inject_custom_css()

st.title("📈 數據探索")

with st.sidebar:
    symbol = st.text_input("標的代碼", value="2330")
    market = st.selectbox("市場", ["TW", "US"])
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("開始日期", value=datetime.now() - timedelta(days=365 * 2))
    with col2:
        end = st.date_input("結束日期", value=datetime.now())

tab1, tab2, tab3, tab4 = st.tabs([
    "台股籌碼" if market == "TW" else "美股期權",
    "qweave 因子掃描",
    "因子診斷",
    "排列檢驗",
])

with tab1:
    if market == "TW":
        st.subheader("台股籌碼因子")
        if st.button("載入籌碼數據", key="load_chips"):
            try:
                with st.spinner("載入中..."):
                    data = tw_chips(symbol=symbol,
                                    start=start.strftime("%Y-%m-%d"),
                                    end=end.strftime("%Y-%m-%d"))
                if not data:
                    st.warning("無籌碼數據")
                else:
                    df = pd.DataFrame(data)
                    if "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                    st.markdown(f"**共 {len(df)} 筆**")
                    st.dataframe(df.tail(50), use_container_width=True, hide_index=True)
            except APIError as e:
                st.error(f"載入失敗：{e}")
    else:
        st.subheader("美股期權因子")
        if st.button("載入期權數據", key="load_options"):
            try:
                with st.spinner("載入中..."):
                    data = us_options(symbol)
                if not data:
                    st.warning("無期權數據")
                else:
                    st.json(data)
                    cols = st.columns(3)
                    keys = ["put_call_volume_ratio", "put_call_oi_ratio",
                            "atm_iv", "iv_skew", "max_pain", "gamma_exposure"]
                    for i, k in enumerate(keys):
                        if k in data:
                            val = data[k]
                            cols[i % 3].metric(k, f"{val:.4f}" if isinstance(val, float) else str(val))
            except APIError as e:
                st.error(f"載入失敗：{e}")

with tab2:
    st.subheader("qweave 因子批量掃描")
    categories = st.multiselect("因子類別", ["alpha101", "alpha158", "alpha191"], default=["alpha158"])
    if st.button("開始掃描", key="run_qweave"):
        if not categories:
            st.warning("請至少選一個類別")
        else:
            try:
                with st.spinner("掃描中..."):
                    data = qweave_batch(symbol=symbol, market=market,
                                        start=start.strftime("%Y-%m-%d"),
                                        end=end.strftime("%Y-%m-%d"),
                                        categories=",".join(categories))
                factors = data.get("factors", {})
                if not factors:
                    st.warning("無因子結果")
                else:
                    st.success(f"共 {len(factors)} 個因子")
                    df = pd.DataFrame([{"factor": k, "value": v} for k, v in factors.items()])
                    st.dataframe(df.sort_values("value", ascending=False),
                                 use_container_width=True, hide_index=True)
            except APIError as e:
                st.error(f"掃描失敗：{e}")

with tab3:
    st.subheader("因子診斷")
    factor_expr = st.text_input("因子表達式", value="rsi(close, 14)", key="inspect_expr")
    if st.button("📊 IC 診斷"):
        try:
            with st.spinner("計算中..."):
                data = inspect_factor(symbol=symbol, market=market,
                                      start=start.strftime("%Y-%m-%d"),
                                      end=end.strftime("%Y-%m-%d"),
                                      factor_expr=factor_expr)
            st.json(data)
        except APIError as e:
            st.error(f"失敗：{e}")

with tab4:
    st.subheader("排列檢驗")
    factor_expr2 = st.text_input("因子表達式", value="rsi(close, 14)", key="validate_expr")
    if st.button("🔬 排列檢驗", key="validate_btn"):
        try:
            with st.spinner("檢驗中（約 30 秒）..."):
                data = validate_factor(symbol=symbol, market=market,
                                       start=start.strftime("%Y-%m-%d"),
                                       end=end.strftime("%Y-%m-%d"),
                                       factor_expr=factor_expr2)
            result = data.get("result", {})
            if result.get("significant"):
                st.success(f"✅ 因子顯著（p={result.get('p_value', 0):.4f}）")
            else:
                st.warning(f"⚠️ 因子不顯著（p={result.get('p_value', 0):.4f}）")
            st.json(data)
        except APIError as e:
            st.error(f"失敗：{e}")
