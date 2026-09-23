"""主題與樣式。"""

import streamlit as st


TW_COLORS = {"up": "#FF4B4B", "down": "#00C853", "flat": "#888888"}
US_COLORS = {"up": "#00C853", "down": "#FF4B4B", "flat": "#888888"}


def get_colors(market: str) -> dict:
    return TW_COLORS if market == "TW" else US_COLORS


def inject_custom_css():
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; opacity: 0.75; }
    [data-testid="stSidebar"] { background-color: #1A1F2E; }
    .dataframe { font-size: 0.85rem; }
    h1 { font-size: 1.8rem !important; }
    h2 { font-size: 1.4rem !important; }
    h3 { font-size: 1.1rem !important; }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-buy { background: #00C853; color: #fff; }
    .badge-sell { background: #FF4B4B; color: #fff; }
    .badge-hold { background: #888; color: #fff; }
    .badge-avoid { background: #666; color: #fff; }
    </style>
    """, unsafe_allow_html=True)


def render_action_badge(action: str) -> str:
    action = action.upper()
    cls = {
        "BUY": "badge-buy", "SELL": "badge-sell",
        "HOLD": "badge-hold", "AVOID": "badge-avoid",
    }.get(action, "badge-hold")
    return f'<span class="badge {cls}">{action}</span>'


def render_metric_row(items: list[tuple], cols: int = 4):
    columns = st.columns(cols)
    for i, item in enumerate(items):
        col = columns[i % cols]
        if len(item) == 3:
            col.metric(item[0], item[1], item[2])
        else:
            col.metric(item[0], item[1])
