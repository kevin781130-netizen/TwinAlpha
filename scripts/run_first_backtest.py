#!/usr/bin/env python3
"""一鍵跑第一次回測並輸出報告。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestEngine
from app.backtest.signal_dsl import SignalDSL
from app.backtest.walk_forward import WalkForwardEngine
from app.data.composite import CompositeProvider
from app.domain.models import Market
from app.risk.guard import build_tw_guard, build_us_guard


PRESET_STRATEGIES = {
    "ma_cross_10_30": {"name": "MA 交叉 (10/30)",
                       "expr": "ema(close, 10) / ema(close, 30) - 1",
                       "upper": 0.02, "lower": -0.02},
    "ma_cross_5_20": {"name": "MA 交叉 (5/20)",
                      "expr": "ema(close, 5) / ema(close, 20) - 1",
                      "upper": 0.01, "lower": -0.01},
    "rsi_14": {"name": "RSI(14) 超買超賣",
               "expr": "rsi(close, 14) - 50",
               "upper": 20, "lower": -20},
    "bollinger": {"name": "布林帶回歸",
                  "expr": "zscore(close, 20)",
                  "upper": 1.5, "lower": -1.5},
    "momentum_20": {"name": "20 日動量",
                    "expr": "close / delay(close, 20) - 1",
                    "upper": 0.05, "lower": -0.05},
}


def compute_metrics(result, bars):
    eq_df = pd.DataFrame(result.get("equity_curve", []))
    if eq_df.empty:
        return {}
    eq_df["return"] = eq_df["equity"].pct_change().fillna(0)
    total_return = float(eq_df["equity"].iloc[-1] / eq_df["equity"].iloc[0] - 1)
    sharpe = float(eq_df["return"].mean() / (eq_df["return"].std() + 1e-9) * (252 ** 0.5))
    cum = eq_df["equity"]
    max_dd = float(((cum / cum.cummax()) - 1).min())
    downside = eq_df["return"][eq_df["return"] < 0]
    sortino = float(eq_df["return"].mean() / (downside.std() + 1e-9) * (252 ** 0.5))
    calmar = float(total_return / (abs(max_dd) + 1e-9))
    annual_vol = float(eq_df["return"].std() * (252 ** 0.5))

    trades = result.get("trades", [])
    wins, losses, buy_stack = 0, 0, []
    holding_days = []
    for t in trades:
        if t["side"] == "BUY":
            buy_stack.append(t)
        elif t["side"] == "SELL" and buy_stack:
            buy = buy_stack.pop(0)
            pnl = (t["price"] - buy["price"]) * t["qty"] - t.get("fee", 0) - buy.get("fee", 0)
            if pnl > 0:
                wins += 1
            else:
                losses += 1
            try:
                days = (pd.Timestamp(t["date"]) - pd.Timestamp(buy["date"])).days
                holding_days.append(days)
            except Exception:
                pass

    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    avg_hold = float(np.mean(holding_days)) if holding_days else 0.0

    return {
        "total_return": round(total_return, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "max_drawdown": round(max_dd, 4),
        "annual_volatility": round(annual_vol, 4),
        "num_trades": len(trades),
        "win_rate": round(win_rate, 4),
        "avg_holding_days": round(avg_hold, 2),
        "final_equity": round(float(eq_df["equity"].iloc[-1]), 2),
        "initial_equity": round(float(eq_df["equity"].iloc[0]), 2),
    }


async def run_single_backtest(data_provider, symbol, market, start, end, strategy,
                              use_risk_guard=False):
    bars = await data_provider.get_bars(symbol, market, start, end)
    if bars is None or bars.empty:
        return {"error": "no data", "symbol": symbol, "market": market.value}
    if len(bars) < 60:
        return {"error": f"insufficient data ({len(bars)} bars)", "symbol": symbol}

    dsl = SignalDSL(bars)
    score = dsl.evaluate(strategy["expr"])
    signals = dsl.discretize(score, strategy["upper"], strategy["lower"])

    risk_guard = None
    if use_risk_guard:
        risk_guard = build_tw_guard() if market == Market.TW else build_us_guard()

    engine = BacktestEngine(market=market, initial_cash=1_000_000.0,
                             slippage_pct=0.001, risk_guard=risk_guard)
    result = engine.run(bars, signals)
    metrics = compute_metrics(result, bars)

    return {
        "symbol": symbol, "market": market.value,
        "strategy": strategy["name"], "expr": strategy["expr"],
        "period": f"{bars['timestamp'].iloc[0].date()} → {bars['timestamp'].iloc[-1].date()}",
        "bars_count": len(bars), "metrics": metrics,
        "trades": result.get("trades", [])[:20],
        "equity_curve": result.get("equity_curve", [])[-100:],
    }


async def run_walk_forward(data_provider, symbol, market, start, end, strategy):
    bars = await data_provider.get_bars(symbol, market, start, end)
    if bars is None or bars.empty or len(bars) < 252 + 63:
        return {"error": "insufficient data"}

    def signal_fn(train_df):
        def gen(test_df):
            dsl = SignalDSL(test_df)
            score = dsl.evaluate(strategy["expr"])
            return dsl.discretize(score, strategy["upper"], strategy["lower"])
        return gen

    def bt(b, s):
        engine = BacktestEngine(market=market, initial_cash=1_000_000.0)
        return engine.run(b, s)

    wf = WalkForwardEngine(train_window=252, test_window=63, step=63)
    result = wf.walk_forward(bars, signal_fn, bt)
    return {"symbol": symbol, "strategy": strategy["name"],
            "summary": result.get("summary", {})}


def generate_markdown_report(results, wf_result, args):
    lines = [f"# 回測報告\n", f"**生成時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
    lines.append("## 一、基本資訊\n")
    lines.append(f"- **標的**：{args.symbol} · **市場**：{args.market}")
    lines.append(f"- **時間範圍**：{args.start} → {args.end}")
    lines.append("")

    lines.append("## 二、策略績效對比\n")
    lines.append("| 策略 | 總報酬 | Sharpe | Sortino | 最大回撤 | 交易數 | 勝率 |")
    lines.append("|------|--------|--------|---------|----------|--------|------|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r.get('strategy', 'N/A')} | ERR | - | - | - | - | - |")
            continue
        m = r.get("metrics", {})
        lines.append(f"| {r['strategy']} | {m.get('total_return', 0):+.2%} | "
                     f"{m.get('sharpe', 0):.2f} | {m.get('sortino', 0):.2f} | "
                     f"{m.get('max_drawdown', 0):.2%} | {m.get('num_trades', 0)} | "
                     f"{m.get('win_rate', 0):.1%} |")
    lines.append("")

    if wf_result and "summary" in wf_result:
        s = wf_result["summary"]
        lines.append("## 三、Walk-Forward 驗證\n")
        lines.append(f"| 指標 | 數值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 窗口數 | {s.get('num_windows', 0)} |")
        lines.append(f"| Sharpe 均值 | {s.get('sharpe_mean', 0):.4f} |")
        lines.append(f"| **OOS 一致性** | **{s.get('oos_consistency', 0):.4f}** |")
        lines.append("")

    lines.append("---\n")
    lines.append("**免責聲明**：本報告僅供研究參考，不構成投資建議。")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="一鍵跑第一次回測")
    parser.add_argument("--symbol", type=str, default="2330")
    parser.add_argument("--market", type=str, default="TW", choices=["TW", "US"])
    parser.add_argument("--start", type=str, default="2022-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--multi", action="store_true")
    parser.add_argument("--expr", type=str, default=None)
    parser.add_argument("--upper", type=float, default=0.02)
    parser.add_argument("--lower", type=float, default=-0.02)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--risk-guard", action="store_true")
    return parser.parse_args()


async def main():
    args = parse_args()
    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    market = Market(args.market)
    data_provider = CompositeProvider()

    print(f"\n{'=' * 70}")
    print(f"回測：{args.symbol} ({args.market}) {args.start} → {args.end}")
    print(f"{'=' * 70}\n")

    if args.expr:
        strategies = [{"name": "自訂策略", "expr": args.expr,
                       "upper": args.upper, "lower": args.lower}]
    elif args.multi:
        strategies = list(PRESET_STRATEGIES.values())
    else:
        strategies = [PRESET_STRATEGIES["ma_cross_10_30"]]

    results = []
    for i, strat in enumerate(strategies, 1):
        print(f"[{i}/{len(strategies)}] {strat['name']} ...")
        result = await run_single_backtest(data_provider, args.symbol, market,
                                            args.start, args.end, strat, args.risk_guard)
        results.append(result)
        if "error" in result:
            print(f"    ❌ {result['error']}")
        else:
            m = result["metrics"]
            print(f"    Sharpe={m['sharpe']:.2f}  Return={m['total_return']:+.2%}  "
                  f"MDD={m['max_drawdown']:.2%}  Trades={m['num_trades']}")

    wf_result = None
    if args.walk_forward and results and "error" not in results[0]:
        print(f"\n跑 Walk-Forward 驗證...")
        wf_result = await run_walk_forward(data_provider, args.symbol, market,
                                            args.start, args.end, strategies[0])
        if "summary" in wf_result:
            print(f"    OOS 一致性: {wf_result['summary'].get('oos_consistency', 0):.4f}")

    md_report = generate_markdown_report(results, wf_result, args)
    md_path = ROOT / "reports" / f"backtest_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)

    json_path = md_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "args": vars(args), "results": results, "walk_forward": wf_result},
                  f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'=' * 70}")
    print(f"報告已生成：\n  Markdown: {md_path}\n  JSON: {json_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
