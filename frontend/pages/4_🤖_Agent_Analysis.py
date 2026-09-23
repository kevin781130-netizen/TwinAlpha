"""Agent 分析頁面。"""

from datetime import datetime, timedelta
import streamlit as st

st.set_page_config(page_title="Agent 分析", page_icon="🤖", layout="wide")

from utils.api_client import analyze, natural_trade, APIError
from utils.theme import inject_custom_css, render_action_badge

inject_custom_css()

st.title("🤖 Agent 分析")

tab1, tab2 = st.tabs(["📊 個股分析", "💬 自然語言下單"])

with tab1:
    with st.sidebar:
        symbol = st.text_input("標的代碼", value="2330", key="agent_symbol")
        market = st.selectbox("市場", ["TW", "US"], key="agent_market")
        col1, col2 = st.columns(2)
        with col1:
            start = st.date_input("開始日期", value=datetime.now() - timedelta(days=180), key="agent_start")
        with col2:
            end = st.date_input("結束日期", value=datetime.now(), key="agent_end")
        run_btn = st.button("🚀 執行分析", type="primary", use_container_width=True)

    if run_btn:
        try:
            with st.spinner("多 Agent 分析中（可能需 1-2 分鐘）..."):
                result = analyze(symbol=symbol, market=market,
                                 start=start.strftime("%Y-%m-%d"),
                                 end=end.strftime("%Y-%m-%d"))
            st.session_state["last_analyze"] = result
        except APIError as e:
            st.error(f"分析失敗：{e}")
            st.stop()

    result = st.session_state.get("last_analyze")
    if not result:
        st.info("👈 左側設定標的，點擊「執行分析」")
        st.stop()

    st.subheader("🎯 最終決策")
    action = result.get("action", "HOLD")
    confidence = result.get("confidence", 0)
    target_pct = result.get("target_position_pct", 0)
    cols = st.columns(4)
    with cols[0]:
        st.markdown("**動作**")
        st.markdown(render_action_badge(action), unsafe_allow_html=True)
    cols[1].metric("信心度", f"{confidence:.0%}")
    cols[2].metric("目標倉位", f"{target_pct:.1%}")
    cols[3].metric("市場", market)

    if result.get("thesis"):
        st.info(result["thesis"])

    st.divider()
    reports = result.get("reports", [])
    if reports:
        st.subheader(f"👥 分析師報告（{len(reports)} 位）")
        for r in reports:
            with st.expander(f"**{r.get('role', '未知')}** — 評分 {r.get('score', 0):+.2f}"):
                st.markdown(f"**結論**：{r.get('summary', '')}")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**關鍵點**")
                    for p in r.get("key_points", []) or []:
                        st.markdown(f"- {p}")
                with col2:
                    st.markdown("**風險**")
                    for risk in r.get("risks", []) or []:
                        st.markdown(f"- ⚠️ {risk}")

    st.divider()
    debate = result.get("debate", {})
    if debate:
        st.subheader("⚔️ 多空辯論")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🐂 多頭觀點")
            st.success(debate.get("bull_case", "無"))
        with col2:
            st.markdown("### 🐻 空頭觀點")
            st.error(debate.get("bear_case", "無"))

    st.divider()
    risk = result.get("risk", {})
    if risk:
        st.subheader("🛡️ 風控審查")
        cols = st.columns(4)
        cols[0].metric("最大倉位", f"{risk.get('max_position_pct', 0):.1%}")
        cols[1].metric("止損", f"{risk.get('stop_loss_pct', 0):.1%}")
        cols[2].metric("止盈", f"{risk.get('take_profit_pct', 0):.1%}")
        cols[3].metric("核准", "✅ 通過" if risk.get("approved") else "❌ 否決")

    st.divider()
    event = result.get("event_driven")
    if event and "error" not in event:
        st.subheader("📰 事件驅動決策")
        cols = st.columns(4)
        cols[0].metric("動作", event.get("action", "-"))
        cols[1].metric("信心度", f"{event.get('confidence', 0):.0%}")
        cols[2].metric("新聞影響", event.get("news_impact", "-"))
        cols[3].metric("關鍵催化劑", (event.get("key_catalyst", "-") or "")[:20])
        if event.get("reasoning"):
            st.info(event["reasoning"])

with tab2:
    st.subheader("💬 自然語言下單")
    user_text = st.text_input("輸入交易指令", value="幫我買一張台積電")
    col1, col2 = st.columns(2)
    with col1:
        portfolio_value = st.number_input("組合總值", value=1_000_000, step=100_000)
    with col2:
        dry_run = st.checkbox("Dry Run（不下單）", value=True)

    if st.button("🚀 執行", type="primary"):
        if not user_text:
            st.warning("請輸入指令")
        else:
            try:
                with st.spinner("解析中..."):
                    result = natural_trade(text=user_text,
                                           portfolio_value=portfolio_value,
                                           dry_run=dry_run)
                st.markdown("### 📋 解析結果")
                st.json(result.get("parsed_intent", {}))
                st.markdown("### 🎬 執行結果")
                execution = result.get("execution", {})
                if execution.get("executed"):
                    st.success("✅ 已執行")
                elif execution.get("dry_run"):
                    st.info("🔵 Dry Run（未實際下單）")
                elif execution.get("reason"):
                    st.warning(f"⚠️ {execution['reason']}")
                else:
                    st.json(execution)
            except APIError as e:
                st.error(f"失敗：{e}")
