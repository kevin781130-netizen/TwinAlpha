#!/usr/bin/env python3
"""17 項本地煙霧測試：不需 Broker 憑證，也不需網路行情。"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd


def synthetic_bars(n=420, symbol="2330", market="TW"):
    rng = np.random.default_rng(42)
    ret = rng.normal(0.0004, 0.012, n)
    close = 100 * np.cumprod(1 + ret)
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="B"),
        "symbol": symbol,
        "market": market,
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1000, 20000, n).astype(float),
    })


async def main():
    passed = 0
    errors = []

    async def run(name, fn):
        nonlocal passed
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                await result
            passed += 1
            print(f"[PASS] {passed:02d}. {name}")
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}"))
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")

    bars = synthetic_bars()

    await run("市場規則層", lambda: _test_market_rules())
    await run("核心資料模型", lambda: _test_models())
    await run("DSL 基礎函數", lambda: _test_dsl_basic(bars))
    await run("DSL 高階函數", lambda: _test_dsl_advanced(bars))
    await run("台股漲跌停 tick", lambda: _test_tw_ticks())
    await run("RiskGuard", lambda: _test_risk())
    await run("BacktestEngine", lambda: _test_backtest(bars))
    await run("WalkForwardEngine", lambda: _test_walk_forward(bars))
    await run("NeutrinoEngine", lambda: _test_neutrino(bars))
    await run("qweave 因子", lambda: _test_qweave(bars))
    await run("因子正交化", lambda: _test_orthogonalize())
    await run("FactorInspector", lambda: _test_inspector(bars))
    await run("ResearchRigor", lambda: _test_rigor())
    await run("MarketRegimeDetector", lambda: _test_regime(bars))
    await run("DuckDB MarketWarehouse", lambda: _test_warehouse(bars))
    await run("FactorRegistry", lambda: _test_registry())
    await run("VerifiableAuditLog", lambda: _test_audit())

    print("\n" + "=" * 60)
    print(f"通過 {passed}/17")
    if errors:
        print(f"失敗 {len(errors)} 項：")
        for name, err in errors:
            print(f"  - {name}: {err}")
        raise SystemExit(1)
    print("17 項全部 PASS")


def _test_market_rules():
    from app.markets.registry import get_rules
    from app.domain.models import Market
    tw, us = get_rules(Market.TW), get_rules(Market.US)
    assert tw.settlement_days == 2 and us.settlement_days == 1
    assert tw.price_limit_pct == 0.10 and us.price_limit_pct is None


def _test_models():
    from app.domain.models import Market, FinalDecision
    d = FinalDecision(symbol="2330", market=Market.TW)
    assert d.action == "HOLD" and d.target_position_pct == 0


def _test_dsl_basic(bars):
    from app.backtest.signal_dsl import SignalDSL
    dsl = SignalDSL(bars)
    for expr in [
        "rsi(close, 14) - 50",
        "ema(close, 10) / ema(close, 30) - 1",
        "zscore(close, 20)",
        "close / delay(close, 5) - 1",
    ]:
        out = dsl.evaluate(expr)
        assert isinstance(out, pd.Series) and len(out) == len(bars)


def _test_dsl_advanced(bars):
    from app.backtest.signal_dsl import SignalDSL
    dsl = SignalDSL(bars)
    for expr in [
        "ts_rank(close, 10)",
        "correlation(open, volume, 10)",
        "quantile(close, 10, 0.8)",
        "rsquare(close, 10)",
        "residual(close, 10)",
    ]:
        out = dsl.evaluate(expr)
        assert isinstance(out, pd.Series)


def _test_tw_ticks():
    from app.markets.taiwan import TaiwanRules
    upper, lower = TaiwanRules().price_limits(100.0)
    assert upper >= 110.0 and lower <= 90.0


def _test_risk():
    from app.risk.guard import build_tw_guard
    g = build_tw_guard()
    g.update_equity(1_000_000)
    g.reset_daily(1_000_000)
    r = g.check_order("2330", "BUY", 1000, 100.0, 1_000_000, 0, 1_000_000)
    assert r["approved"] and r["adjusted_qty"] <= 1500


def _test_backtest(bars):
    from app.backtest.engine import BacktestEngine
    from app.backtest.signal_dsl import SignalDSL
    from app.domain.models import Market
    dsl = SignalDSL(bars)
    sig = dsl.discretize(dsl.evaluate("ema(close,10)/ema(close,30)-1"), 0.005, -0.005)
    r = BacktestEngine(Market.TW).run(bars, sig)
    assert "equity_curve" in r and len(r["equity_curve"]) > 0


def _test_walk_forward(bars):
    from app.backtest.walk_forward import WalkForwardEngine
    from app.backtest.engine import BacktestEngine
    from app.backtest.signal_dsl import SignalDSL
    from app.domain.models import Market

    def signal_fn(_train):
        def gen(test):
            dsl = SignalDSL(test)
            return dsl.discretize(dsl.evaluate("ema(close,5)/ema(close,20)-1"), 0.002, -0.002)
        return gen

    def bt(test, signals):
        return BacktestEngine(Market.TW).run(test, signals)

    r = WalkForwardEngine(train_window=200, test_window=50, step=50).walk_forward(bars, signal_fn, bt)
    assert "windows" in r and len(r["windows"]) >= 1


def _test_neutrino(bars):
    from app.backtest.neutrino_engine import NeutrinoEngine
    s = np.where(pd.Series(bars["close"]).rolling(10).mean().bfill() < bars["close"], 1, 0)
    r = NeutrinoEngine().vectorized_backtest(bars["close"].to_numpy(), s)
    assert "error" not in r and "sharpe" in r


def _test_qweave(bars):
    from app.factors.qweave_loader import QweaveFactorLoader
    r = QweaveFactorLoader.batch_evaluate(bars, ["alpha158"])
    assert isinstance(r, dict)


def _test_orthogonalize():
    from app.factors.orthogonalize import FactorOrthogonalizer
    rng = np.random.default_rng(1)
    x = pd.DataFrame(rng.normal(size=(100, 3)), columns=["a", "b", "c"])
    out = FactorOrthogonalizer.gram_schmidt(x)
    assert out.shape == x.shape


def _test_inspector(bars):
    from app.factors.inspect import FactorInspector
    f = pd.DataFrame({"mom": bars["close"].pct_change(5)})
    r = FactorInspector(bars, f, ["mom"]).full_report("mom")
    assert "ic" in r and "decay" in r


def _test_rigor():
    from app.research.rigor import ResearchRigor
    rng = np.random.default_rng(7)
    f = rng.normal(size=80)
    r = 0.05 * f + rng.normal(size=80)
    out = ResearchRigor(min_samples=30).permutation_test(f, r, n_permutations=50)
    assert "p_value" in out


def _test_regime(bars):
    from app.execution.reasoning_engine import MarketRegimeDetector
    r = MarketRegimeDetector.detect(bars, lookback=60)
    assert r["regime"] in {"unknown", "sideways", "high_vol_bull", "low_vol_bull", "high_vol_bear", "low_vol_bear"}


def _test_warehouse(bars):
    from app.data.warehouse import MarketWarehouse
    from app.domain.models import Market
    with tempfile.TemporaryDirectory() as td:
        w = MarketWarehouse(Path(td) / "market.duckdb")
        w.upsert_bars(bars.head(30))
        out = w.query_bars("2330", Market.TW)
        assert len(out) == 30


def _test_registry():
    from app.factors.registry import FactorRegistry
    with tempfile.TemporaryDirectory() as td:
        r = FactorRegistry(str(Path(td) / "factors.duckdb"))
        fid = r.register("test_factor", "close/delay(close,5)-1", market="TW")
        out = r.validate(fid, 0.02, 0.03, 0.01)
        assert out["status"] == "production"


def _test_audit():
    from app.audit.verifiable_log import VerifiableAuditLog
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "events.jsonl"
        log = VerifiableAuditLog(str(p))
        log.append("TEST", {"x": 1})
        log.append("TEST", {"x": 2})
        result = log.verify_integrity()
        assert result["valid"] and result["total_records"] == 2


if __name__ == "__main__":
    asyncio.run(main())
