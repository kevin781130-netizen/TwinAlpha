import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import InvestmentOrchestrator
from app.agents.nl_trader import NLTrader
from app.backtest.engine import BacktestEngine
from app.backtest.neutrino_engine import NeutrinoEngine
from app.backtest.signal_dsl import SignalDSL
from app.backtest.walk_forward import WalkForwardEngine
from app.data.composite import CompositeProvider
from app.domain.models import Market, Side
from app.factors.inspect import FactorInspector
from app.factors.qweave_loader import QweaveFactorLoader
from app.factors.tw_chips import TWChipsFactorEngine
from app.factors.us_options import USOptionsFactorEngine
from app.markets.registry import get_rules
from app.portfolio.optimizer import PortfolioOptimizer
from app.research.rigor import ResearchRigor
from app.risk.guard import build_tw_guard, build_us_guard

app = FastAPI(title="TW/US Invest OS", version="0.5.0")

orchestrator = InvestmentOrchestrator()
data_provider = CompositeProvider()
_nl_trader = NLTrader()
_risk_tw = build_tw_guard()
_risk_us = build_us_guard()


class AnalyzeReq(BaseModel):
    symbol: str
    market: Market
    start: str = "2024-01-01"
    end: str = "2025-01-01"


class BacktestReq(BaseModel):
    symbol: str
    market: Market
    start: str
    end: str
    expr: str = "ema(close, 10) / ema(close, 30) - 1"
    upper: float = 0.02
    lower: float = -0.02


def _guard(market: Market):
    return _risk_tw if market == Market.TW else _risk_us


def _metrics(result: dict) -> dict:
    eq = pd.DataFrame(result.get("equity_curve", []))
    if not eq.empty and "equity" in eq.columns and len(eq) > 1:
        eq["return"] = eq["equity"].pct_change()
        sharpe = (eq["return"].mean() / (eq["return"].std() + 1e-9)) * (252 ** 0.5)
        total_return = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
        max_dd = ((eq["equity"] / eq["equity"].cummax()) - 1).min()
    else:
        sharpe = total_return = max_dd = 0.0
    return {
        "sharpe": round(float(sharpe), 4),
        "total_return": round(float(total_return), 4),
        "max_drawdown": round(float(max_dd), 4),
        "num_trades": len(result.get("trades", [])),
    }


async def _load_bars(symbol: str, market: Market, start: str, end: str) -> pd.DataFrame:
    bars = await data_provider.get_bars(symbol, market, start, end)
    if bars is None or bars.empty:
        raise HTTPException(status_code=404, detail="no data")
    return bars


@app.get("/health")
def health():
    return {"ok": True, "app": "TW/US Invest OS"}


@app.get("/rules/{market}")
def rules(market: Market):
    r = get_rules(market)
    return {
        "market": market.value,
        "settlement_days": r.settlement_days,
        "price_limit_pct": r.price_limit_pct,
        "lot_size": r.lot_size,
    }


@app.post("/analyze")
async def analyze(req: AnalyzeReq):
    return await orchestrator.analyze(req.symbol, req.market, req.start, req.end)


@app.post("/backtest")
async def backtest(req: BacktestReq):
    bars = await _load_bars(req.symbol, req.market, req.start, req.end)
    dsl = SignalDSL(bars)
    score = dsl.evaluate(req.expr)
    signals = dsl.discretize(score, req.upper, req.lower)
    result = BacktestEngine(market=req.market).run(bars, signals)
    result["metrics"] = _metrics(result)
    return result


@app.post("/backtest/walk-forward")
async def backtest_walk_forward(
    symbol: str,
    market: Market,
    start: str,
    end: str,
    expr: str = "ema(close,10)/ema(close,30)-1",
    upper: float = 0.02,
    lower: float = -0.02,
    train_window: int = 252,
    test_window: int = 63,
    step: int = 63,
):
    bars = await _load_bars(symbol, market, start, end)
    if len(bars) < train_window + test_window:
        raise HTTPException(status_code=400, detail="insufficient data for walk-forward")

    def signal_fn(_train):
        def generate(test):
            dsl = SignalDSL(test)
            return dsl.discretize(dsl.evaluate(expr), upper, lower)
        return generate

    def backtest_fn(test, signals):
        return BacktestEngine(market=market).run(test, signals)

    wf = WalkForwardEngine(train_window=train_window, test_window=test_window, step=step)
    return wf.walk_forward(bars, signal_fn, backtest_fn)


@app.post("/backtest/sweep")
async def backtest_sweep(
    symbol: str,
    market: Market,
    start: str,
    end: str,
    fast_range: str = "5,10,15,20",
    slow_range: str = "20,30,40,50",
):
    bars = await _load_bars(symbol, market, start, end)
    try:
        fast_values = [int(x.strip()) for x in fast_range.split(",") if x.strip()]
        slow_values = [int(x.strip()) for x in slow_range.split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid range: {e}")

    def strategy(close, fast, slow):
        s = pd.Series(close)
        f = s.ewm(span=int(fast), adjust=False).mean()
        sl = s.ewm(span=int(slow), adjust=False).mean()
        return np.where(f > sl, 1.0, 0.0)

    result = NeutrinoEngine().parameter_sweep(
        bars,
        strategy,
        {"fast": fast_values, "slow": slow_values},
    )
    if result.empty:
        return []
    return result.replace([np.inf, -np.inf], np.nan).where(pd.notna(result), None).to_dict("records")


@app.post("/factors/tw-chips")
def factors_tw_chips(symbol: str, start: str, end: str):
    df = TWChipsFactorEngine().compute_factors(symbol, start, end)
    if df is None or df.empty:
        return []
    return df.where(pd.notna(df), None).to_dict("records")


@app.post("/factors/us-options")
def factors_us_options(symbol: str):
    return USOptionsFactorEngine().compute_factors(symbol)


@app.post("/factors/qweave/batch")
async def factors_qweave_batch(
    symbol: str,
    market: Market,
    start: str,
    end: str,
    categories: str = "alpha158",
):
    bars = await _load_bars(symbol, market, start, end)
    cats = [x.strip() for x in categories.split(",") if x.strip()]
    factors = QweaveFactorLoader.batch_evaluate(bars, cats)
    return {"symbol": symbol, "market": market.value, "categories": cats, "factors": factors}


@app.post("/factors/inspect")
async def factors_inspect(
    symbol: str,
    market: Market,
    start: str,
    end: str,
    factor_expr: str,
):
    bars = await _load_bars(symbol, market, start, end)
    score = SignalDSL(bars).evaluate(factor_expr)
    factors = pd.DataFrame({"factor": score})
    report = FactorInspector(bars, factors, ["factor"]).full_report("factor")
    return {"symbol": symbol, "market": market.value, "factor_expr": factor_expr, **report}


@app.post("/research/validate-factor")
async def validate_factor(
    symbol: str,
    market: Market,
    start: str,
    end: str,
    factor_expr: str,
    n_permutations: int = 1000,
):
    bars = await _load_bars(symbol, market, start, end)
    factor = SignalDSL(bars).evaluate(factor_expr).astype(float)
    forward = bars["close"].pct_change().shift(-1).astype(float)
    result = ResearchRigor().permutation_test(
        factor.to_numpy(), forward.to_numpy(), n_permutations=n_permutations
    )
    return {
        "factor": factor_expr,
        "result": result,
        "verdict": "因子顯著" if result.get("significant") else "因子不顯著",
    }


@app.post("/portfolio/optimize")
async def portfolio_optimize(
    symbols: str,
    market: Market,
    start: str,
    end: str,
    method: str = "hrp",
    max_weight: float = 0.3,
):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 assets")

    # Ensure requested history is cached before the optimizer reads the warehouse.
    for symbol in symbol_list:
        try:
            await data_provider.get_bars(symbol, market, start, end)
        except Exception:
            pass

    optimizer = PortfolioOptimizer()
    returns = optimizer.load_returns(symbol_list, market, start, end)
    return optimizer.optimize(returns, method=method, max_weight=max_weight)


@app.post("/risk/check")
def risk_check(
    market: Market,
    symbol: str,
    side: Side,
    qty: int,
    price: float,
    portfolio_value: float,
    current_position_value: float = 0.0,
    current_equity: float = 1_000_000.0,
):
    return _guard(market).check_order(
        symbol, side.value, qty, price,
        portfolio_value, current_position_value, current_equity,
    )


@app.post("/risk/kill-switch")
def kill_switch(reason: str = "manual", market: Market | None = None):
    if market is None:
        return {
            "TW": _risk_tw.activate_kill_switch(reason),
            "US": _risk_us.activate_kill_switch(reason),
        }
    return _guard(market).activate_kill_switch(reason)


@app.post("/trade/order-protected")
async def place_order_protected(
    symbol: str,
    market: Market,
    side: Side,
    price: float,
    qty: int,
    portfolio_value: float,
    current_position_value: float = 0.0,
    current_equity: float = 1_000_000.0,
    dry_run: bool = True,
):
    check = _guard(market).check_order(
        symbol, side.value, qty, price,
        portfolio_value, current_position_value, current_equity,
    )
    if not check["approved"]:
        return {"blocked": True, "reason": check["reason"]}

    adjusted_qty = check.get("adjusted_qty", qty)
    if dry_run:
        return {
            "dry_run": True,
            "symbol": symbol,
            "side": side.value,
            "original_qty": qty,
            "adjusted_qty": adjusted_qty,
            "reason": check["reason"],
        }

    # Live broker wiring stays intentionally disabled until credentials and paper tests are verified.
    return {
        "dry_run": False,
        "message": "broker integration not enabled",
        "adjusted_qty": adjusted_qty,
    }


@app.post("/trade/natural")
async def natural_language_trade(
    text: str,
    portfolio_value: float = 1_000_000,
    dry_run: bool = True,
):
    intent = await _nl_trader.parse_intent(text, {"portfolio_value": portfolio_value})
    from app.broker.shioaji_bridge import ShioajiBridge
    from app.broker.ibkr_bridge import IBKRBridge

    result = await _nl_trader.execute(
        intent,
        _risk_tw,
        ShioajiBridge(simulation=True),
        IBKRBridge(port=4002, paper=True),
        dry_run,
    )
    return {"input": text, "parsed_intent": intent, "execution": result}


@app.get("/trade/audit-log")
async def get_audit_log(limit: int = 100):
    return _nl_trader.get_audit_log(limit)
