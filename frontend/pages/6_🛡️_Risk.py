"""風控頁面。"""

import streamlit as st

st.set_page_config(page_title="風控", page_icon="🛡️", layout="wide")

from utils.api_client import check_risk, activate_kill_switch, order_protected, APIError
from utils.theme import inject_custom_css

inject_custom_css()

st.title("🛡️ 風控")

tab1, tab2, tab3 = st.tabs(["風控檢查", "下單測試", "緊急處理"])

with tab1:
    st.subheader("下單前風控檢查")
    col1, col2 = st.columns(2)
    with col1:
        market = st.selectbox("市場", ["TW", "US"], key="risk_market")
        symbol = st.text_input("標的代碼", value="2330", key="risk_symbol")
        side = st.selectbox("方向", ["BUY", "SELL"])
    with col2:
        price = st.number_input("價格", value=850.0, min_value=0.0)
        qty = st.number_input("數量", value=1000, min_value=1, step=100)
        portfolio_value = st.number_input("組合總值", value=1_000_000, step=100_000)

    current_position_value = st.number_input("當前持倉市值", value=0.0, min_value=0.0, step=10_000.0)
    current_equity = st.number_input("當前權益", value=1_000_000, step=100_000)

    if st.button("🔍 檢查", type="primary"):
        try:
            result = check_risk(
                market=market, symbol=symbol, side=side,
                qty=int(qty), price=price,
                portfolio_value=portfolio_value,
                current_position_value=current_position_value,
                current_equity=current_equity,
            )
            if result.get("approved"):
                st.success("✅ 核准通過")
            else:
                st.error("❌ 風控攔截")
            st.json(result)
        except APIError as e:
            st.error(f"檢查失敗：{e}")

with tab2:
    st.subheader("帶風控的下單測試")
    col1, col2 = st.columns(2)
    with col1:
        market2 = st.selectbox("市場", ["TW", "US"], key="order_market")
        symbol2 = st.text_input("標的代碼", value="2330", key="order_symbol")
        side2 = st.selectbox("方向", ["BUY", "SELL"], key="order_side")
    with col2:
        price2 = st.number_input("價格", value=850.0, min_value=0.0, key="order_price")
        qty2 = st.number_input("數量", value=1000, min_value=1, step=100, key="order_qty")
        portfolio_value2 = st.number_input("組合總值", value=1_000_000, step=100_000, key="order_pv")

    dry_run = st.checkbox("Dry Run（不下單）", value=True)

    if st.button("🚀 執行下單測試", type="primary"):
        try:
            result = order_protected(
                symbol=symbol2, market=market2, side=side2,
                price=price2, qty=int(qty2),
                portfolio_value=portfolio_value2, dry_run=dry_run,
            )
            if result.get("blocked"):
                st.error(f"❌ 風控攔截：{result.get('reason')}")
            elif result.get("dry_run"):
                st.info("🔵 Dry Run 通過")
                st.json(result)
            else:
                st.success("✅ 執行成功")
                st.json(result)
        except APIError as e:
            st.error(f"失敗：{e}")

with tab3:
    st.subheader("⚠️ 緊急處理")
    st.warning("Kill Switch 會立即停止所有交易並進入冷卻期。**只在緊急情況下使用**。")
    reason = st.text_input("原因", value="manual", key="ks_reason")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🛑 觸發 Kill Switch", type="primary"):
            try:
                result = activate_kill_switch(reason=reason)
                st.error("🚨 Kill Switch 已觸發")
                st.json(result)
            except APIError as e:
                st.error(f"失敗：{e}")
    with col2:
        st.markdown("""
        **恢復步驟**：
        1. 確認市場環境已穩定
        2. 檢查持倉與未平倉訂單
        3. 重新啟動後端服務
        4. 或刪除 `data_lake/risk_state_*.json`
        """)
