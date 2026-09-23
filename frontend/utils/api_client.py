"""FastAPI 客戶端封裝。"""

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st


API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 60


class APIError(Exception):
    pass


def _handle_response(r: requests.Response) -> Any:
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise APIError(f"HTTP {r.status_code}: {detail}")
    try:
        return r.json()
    except Exception:
        return r.text


@st.cache_data(ttl=30, show_spinner=False)
def health_check() -> dict:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        return _handle_response(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def get_rules(market: str) -> dict:
    r = requests.get(f"{API_BASE}/rules/{market}", timeout=TIMEOUT)
    return _handle_response(r)


def run_backtest(symbol, market, start, end, expr, upper, lower) -> dict:
    payload = {"symbol": symbol, "market": market, "start": start,
               "end": end, "expr": expr, "upper": upper, "lower": lower}
    r = requests.post(f"{API_BASE}/backtest", json=payload, timeout=TIMEOUT)
    return _handle_response(r)


def run_walk_forward(symbol, market, start, end, expr="ema(close,10)/ema(close,30)-1",
                     train_window=252, test_window=63) -> dict:
    params = {"symbol": symbol, "market": market, "start": start, "end": end,
              "expr": expr, "train_window": train_window, "test_window": test_window}
    r = requests.post(f"{API_BASE}/backtest/walk-forward", params=params, timeout=TIMEOUT * 3)
    return _handle_response(r)


def sweep_parameters(symbol, market, start, end, fast_range, slow_range) -> list:
    params = {"symbol": symbol, "market": market, "start": start,
              "end": end, "fast_range": fast_range, "slow_range": slow_range}
    r = requests.post(f"{API_BASE}/backtest/sweep", params=params, timeout=TIMEOUT * 3)
    return _handle_response(r)


def analyze(symbol, market, start, end) -> dict:
    payload = {"symbol": symbol, "market": market, "start": start, "end": end}
    r = requests.post(f"{API_BASE}/analyze", json=payload, timeout=TIMEOUT * 3)
    return _handle_response(r)


def tw_chips(symbol, start, end) -> list:
    params = {"symbol": symbol, "start": start, "end": end}
    r = requests.post(f"{API_BASE}/factors/tw-chips", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def us_options(symbol) -> dict:
    r = requests.post(f"{API_BASE}/factors/us-options", params={"symbol": symbol}, timeout=TIMEOUT)
    return _handle_response(r)


def qweave_batch(symbol, market, start, end, categories="alpha158") -> dict:
    params = {"symbol": symbol, "market": market, "start": start,
              "end": end, "categories": categories}
    r = requests.post(f"{API_BASE}/factors/qweave/batch", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def inspect_factor(symbol, market, start, end, factor_expr) -> dict:
    params = {"symbol": symbol, "market": market, "start": start,
              "end": end, "factor_expr": factor_expr}
    r = requests.post(f"{API_BASE}/factors/inspect", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def validate_factor(symbol, market, start, end, factor_expr) -> dict:
    params = {"symbol": symbol, "market": market, "start": start,
              "end": end, "factor_expr": factor_expr}
    r = requests.post(f"{API_BASE}/research/validate-factor", params=params, timeout=TIMEOUT * 2)
    return _handle_response(r)


def optimize_portfolio(symbols, market, start, end, method="hrp") -> dict:
    params = {"symbols": symbols, "market": market, "start": start,
              "end": end, "method": method}
    r = requests.post(f"{API_BASE}/portfolio/optimize", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def check_risk(market, symbol, side, qty, price, portfolio_value,
               current_position_value=0.0, current_equity=1_000_000.0) -> dict:
    params = {"market": market, "symbol": symbol, "side": side, "qty": qty,
              "price": price, "portfolio_value": portfolio_value,
              "current_position_value": current_position_value,
              "current_equity": current_equity}
    r = requests.post(f"{API_BASE}/risk/check", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def activate_kill_switch(reason="manual") -> dict:
    r = requests.post(f"{API_BASE}/risk/kill-switch", params={"reason": reason}, timeout=TIMEOUT)
    return _handle_response(r)


def order_protected(symbol, market, side, price, qty, portfolio_value, dry_run=True) -> dict:
    params = {"symbol": symbol, "market": market, "side": side, "price": price,
              "qty": qty, "portfolio_value": portfolio_value, "dry_run": dry_run}
    r = requests.post(f"{API_BASE}/trade/order-protected", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def natural_trade(text, portfolio_value=1_000_000, dry_run=True) -> dict:
    params = {"text": text, "portfolio_value": portfolio_value, "dry_run": dry_run}
    r = requests.post(f"{API_BASE}/trade/natural", params=params, timeout=TIMEOUT)
    return _handle_response(r)


def get_audit_log(limit=100) -> list:
    r = requests.get(f"{API_BASE}/trade/audit-log", params={"limit": limit}, timeout=TIMEOUT)
    return _handle_response(r)
