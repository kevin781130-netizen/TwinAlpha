"""Generated compatibility helper for the supplied Streamlit dashboard."""
import streamlit as st

def backtest_metrics(metrics: dict):
    cols = st.columns(4)
    cols[0].metric("總報酬", f"{metrics.get('total_return', 0):+.2%}")
    cols[1].metric("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
    cols[2].metric("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}")
    cols[3].metric("交易次數", str(metrics.get('num_trades', 0)))
