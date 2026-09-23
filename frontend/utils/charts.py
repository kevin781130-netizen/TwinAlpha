"""Plotly 圖表封裝。"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go


LAYOUT_BASE = {
    "template": "plotly_dark",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#FAFAFA"},
    "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
    "hovermode": "x unified",
}


def equity_curve_chart(equity_curve: list, title: str = "權益曲線") -> go.Figure:
    if not equity_curve:
        return _empty_chart("無數據")
    df = pd.DataFrame(equity_curve)
    if "date" not in df.columns or "equity" not in df.columns:
        return _empty_chart("數據格式錯誤")
    df["date"] = pd.to_datetime(df["date"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["equity"], mode="lines", name="權益",
        line=dict(color="#00A3A3", width=2),
        fill="tozeroy", fillcolor="rgba(0,163,163,0.1)",
    ))
    fig.update_layout(**LAYOUT_BASE, title=title,
                      xaxis_title="日期", yaxis_title="權益")
    return fig


def price_chart(df: pd.DataFrame, title: str = "價格", market: str = "TW") -> go.Figure:
    if df is None or df.empty:
        return _empty_chart("無數據")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    up_color = "#FF4B4B" if market == "TW" else "#00C853"
    down_color = "#00C853" if market == "TW" else "#FF4B4B"

    fig = go.Figure(data=[go.Candlestick(
        x=df["timestamp"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=up_color, decreasing_line_color=down_color,
        name="K線",
    )])
    fig.update_layout(**LAYOUT_BASE, title=title,
                      xaxis_title="日期", yaxis_title="價格",
                      xaxis_rangeslider_visible=False)
    return fig


def returns_histogram(equity_curve: list, title: str = "日報酬分佈") -> go.Figure:
    if not equity_curve:
        return _empty_chart("無數據")
    df = pd.DataFrame(equity_curve)
    if "equity" not in df.columns:
        return _empty_chart("無數據")
    returns = df["equity"].pct_change().dropna() * 100

    fig = go.Figure(data=[go.Histogram(x=returns, nbinsx=50, marker_color="#00A3A3")])
    fig.update_layout(**LAYOUT_BASE, title=title,
                      xaxis_title="日報酬 (%)", yaxis_title="頻次")
    return fig


def drawdown_chart(equity_curve: list, title: str = "回撤") -> go.Figure:
    if not equity_curve:
        return _empty_chart("無數據")
    df = pd.DataFrame(equity_curve)
    if "date" not in df.columns or "equity" not in df.columns:
        return _empty_chart("無數據")
    df["date"] = pd.to_datetime(df["date"])
    cum = df["equity"]
    dd = (cum / cum.cummax() - 1) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=dd, mode="lines", name="回撤",
        line=dict(color="#FF4B4B", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,75,75,0.2)",
    ))
    fig.update_layout(**LAYOUT_BASE, title=title,
                      xaxis_title="日期", yaxis_title="回撤 (%)")
    return fig


def portfolio_weights(weights: dict, title: str = "組合權重") -> go.Figure:
    if not weights:
        return _empty_chart("無數據")
    fig = go.Figure(data=[go.Pie(
        labels=list(weights.keys()), values=list(weights.values()),
        hole=0.5, textinfo="label+percent",
        marker=dict(colors=["#00A3A3", "#FF8C42", "#5B8FF9", "#5AD8A6",
                            "#F6BD16", "#E8684A", "#6DC8EC", "#9270CA"]),
    )])
    fig.update_layout(**LAYOUT_BASE, title=title)
    return fig


def factor_ic_bar(ic_data: list, title: str = "因子 IC") -> go.Figure:
    if not ic_data:
        return _empty_chart("無數據")
    df = pd.DataFrame(ic_data)
    if "factor" not in df.columns or "IC" not in df.columns:
        return _empty_chart("數據格式錯誤")
    df = df.sort_values("IC", ascending=True)
    colors = ["#00C853" if v > 0 else "#FF4B4B" for v in df["IC"]]

    fig = go.Figure(data=[go.Bar(x=df["IC"], y=df["factor"],
                                  orientation="h", marker_color=colors)])
    fig.update_layout(**LAYOUT_BASE, title=title,
                      xaxis_title="IC", yaxis_title="因子")
    return fig


def _empty_chart(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16, color="#888"))
    fig.update_layout(**LAYOUT_BASE)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig
