#!/usr/bin/env python3
"""Shioaji 台股模擬盤自動交易腳本。"""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime, time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.audit.verifiable_log import VerifiableAuditLog
from app.backtest.signal_dsl import SignalDSL
from app.broker.shioaji_bridge import ShioajiBridge
from app.data.composite import CompositeProvider
from app.domain.models import Market, Side
from app.risk.guard import build_tw_guard


TW_TRADING_START = dtime(9, 0)
TW_TRADING_END = dtime(13, 30)
STATE_PATH = ROOT / "data_lake" / "paper_trading_state.json"
LOG_PATH = ROOT / "data_lake" / "audit" / "paper_trading.jsonl"
TRADE_LOG_PATH = ROOT / "data_lake" / "paper_trading_trades.jsonl"


class MACrossStrategy:
    name = "ma_cross"
    def __init__(self, fast=10, slow=30, upper=0.02, lower=-0.02):
        self.fast, self.slow = fast, slow
        self.upper, self.lower = upper, lower

    def generate_signals(self, bars):
        dsl = SignalDSL(bars)
        expr = f"ema(close, {self.fast}) / ema(close, {self.slow}) - 1"
        score = dsl.evaluate(expr)
        return dsl.discretize(score, self.upper, self.lower)


class RSIStrategy:
    name = "rsi"
    def __init__(self, window=14, oversold=30, overbought=70):
        self.window, self.oversold, self.overbought = window, oversold, overbought

    def generate_signals(self, bars):
        dsl = SignalDSL(bars)
        rsi = dsl.evaluate(f"rsi(close, {self.window})")
        signals = pd.Series(0, index=bars.index)
        signals[rsi < self.oversold] = 1
        signals[rsi > self.overbought] = -1
        return signals


class TradingState:
    def __init__(self):
        self.positions = {}
        self.trades_today = []
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.peak_equity = 0.0
        self.circuit_breaker_active = False
        self.last_reset_date = ""

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"positions": self.positions, "trades_today": self.trades_today[-20:],
                       "daily_pnl": self.daily_pnl, "daily_trade_count": self.daily_trade_count,
                       "peak_equity": self.peak_equity,
                       "circuit_breaker_active": self.circuit_breaker_active,
                       "last_reset_date": self.last_reset_date,
                       "saved_at": datetime.now().isoformat()},
                      f, indent=2, ensure_ascii=False)


class PaperTradingBot:
    def __init__(self, symbols, strategy, interval_sec=300, dry_run=False,
                 initial_cash=1_000_000.0, max_position_pct=0.15):
        self.symbols = symbols
        self.strategy = strategy
        self.interval_sec = interval_sec
        self.dry_run = dry_run
        self.initial_cash = initial_cash
        self.broker = ShioajiBridge(simulation=True)
        self.data = CompositeProvider()
        self.risk = build_tw_guard()
        self.risk.max_position_pct = max_position_pct
        self.audit = VerifiableAuditLog(log_path=str(LOG_PATH))
        self.state = TradingState()
        self.running = False
        self.last_prices = {}
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\n[INFO] 收到中斷信號，準備優雅退出...")
        self.running = False

    async def run(self):
        if not self.dry_run:
            self.broker.connect()
        self.running = True
        print(f"\n{'=' * 60}")
        print(f"模擬盤啟動 · 標的: {', '.join(self.symbols)} · "
              f"策略: {self.strategy.name} · 模式: "
              f"{'DRY RUN' if self.dry_run else '模擬下單'}")
        print(f"{'=' * 60}\n")

        iteration = 0
        while self.running:
            iteration += 1
            try:
                if not self._is_trading_hours():
                    await asyncio.sleep(min(self.interval_sec, 60))
                    continue
                await self._scan_and_trade()
                self._update_pnl()
                self.state.save(STATE_PATH)
                self._print_status()
            except Exception as e:
                print(f"[ERROR] {e}")
                self.audit.append("SYSTEM_ERROR", {"error": str(e)})

            for _ in range(self.interval_sec):
                if not self.running:
                    break
                await asyncio.sleep(1)

        self._shutdown()

    def _is_trading_hours(self):
        now = datetime.now().time()
        return TW_TRADING_START <= now <= TW_TRADING_END

    async def _scan_and_trade(self):
        for symbol in self.symbols:
            try:
                await self._process_symbol(symbol)
            except Exception as e:
                print(f"[ERROR] {symbol}: {e}")

    async def _process_symbol(self, symbol):
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - pd.Timedelta(days=180)).strftime("%Y-%m-%d")

        bars = await self.data.get_bars(symbol, Market.TW, start, end)
        if bars is None or bars.empty or len(bars) < 60:
            return

        signals = self.strategy.generate_signals(bars)
        latest_signal = float(signals.iloc[-1])
        latest_price = float(bars["close"].iloc[-1])
        self.last_prices[symbol] = latest_price

        action = self._decide_action(symbol, latest_signal)
        if action == "NONE":
            print(f"[{symbol}] 價格 {latest_price:.2f}，信號 {latest_signal:+.0f}，無動作")
            return

        portfolio_value = self.initial_cash
        for sym, pos in self.state.positions.items():
            px = self.last_prices.get(sym, pos.get("avg_cost", 0))
            portfolio_value += pos.get("qty", 0) * px

        current = self.state.positions.get(symbol, {})
        current_qty = int(current.get("qty", 0))
        current_position_value = current_qty * latest_price

        if action == "BUY":
            qty = max(1, int((portfolio_value * self.risk.max_position_pct) / latest_price))
            side = Side.BUY
        else:
            qty = current_qty
            side = Side.SELL

        check = self.risk.check_order(
            symbol=symbol, side=side.value, qty=qty, price=latest_price,
            portfolio_value=portfolio_value,
            current_position_value=current_position_value,
            current_equity=portfolio_value,
        )
        if not check.get("approved"):
            print(f"[{symbol}] 風控攔截: {check.get('reason')}")
            self.audit.log_risk_check(symbol, False, check.get("reason", "REJECT"))
            return

        qty = int(check.get("adjusted_qty", qty))
        if qty <= 0:
            print(f"[{symbol}] 風控調整後數量為 0")
            return

        self.audit.log_risk_check(symbol, True, check.get("reason", "PASS"))

        status = "DRY_RUN"
        result = {"simulation": True, "dry_run": self.dry_run}
        if not self.dry_run:
            result = self.broker.place_order(
                symbol=symbol, side=side, price=latest_price, qty=qty,
                price_type="LMT", order_type="ROD",
            )
            if result.get("error"):
                print(f"[{symbol}] 下單失敗: {result['error']}")
                self.audit.append("ORDER_ERROR", {"symbol": symbol, "result": result})
                return
            status = result.get("status", "SUBMITTED")

        if side == Side.BUY:
            self.state.positions[symbol] = {"qty": qty, "avg_cost": latest_price}
        else:
            self.state.positions.pop(symbol, None)

        trade = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol, "side": side.value, "qty": qty,
            "price": latest_price, "status": status,
            "dry_run": self.dry_run,
        }
        self.state.trades_today.append(trade)
        self.state.daily_trade_count += 1
        TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRADE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(trade, ensure_ascii=False) + "\n")

        self.audit.log_order(
            result.get("order_id", f"dry-{self.state.daily_trade_count}"),
            symbol, side.value, qty, latest_price, status,
        )
        print(f"[{symbol}] {side.value} {qty} @ {latest_price:.2f} · {status}")

    def _decide_action(self, symbol, signal):
        qty = self.state.positions.get(symbol, {}).get("qty", 0)
        if signal > 0 and qty == 0:
            return "BUY"
        if signal < 0 and qty > 0:
            return "SELL"
        return "NONE"

    def _update_pnl(self):
        total_pnl = 0.0
        for symbol, pos in self.state.positions.items():
            cur = self.last_prices.get(symbol)
            if cur is None:
                continue
            total_pnl += (cur - pos.get("avg_cost", 0)) * pos.get("qty", 0)
        self.state.daily_pnl = round(total_pnl, 2)

    def _print_status(self):
        positions_str = ", ".join([f"{s}:{p['qty']}@{p['avg_cost']}"
                                    for s, p in self.state.positions.items()]) or "無"
        print(f"\n--- 狀態 {datetime.now().strftime('%H:%M:%S')} ---")
        print(f"  當日盈虧: {self.state.daily_pnl:+,.0f} · "
              f"交易: {self.state.daily_trade_count} 筆")
        print(f"  持倉: {positions_str}")

    def _shutdown(self):
        print("\n[INFO] 保存狀態...")
        self.state.save(STATE_PATH)
        v = self.audit.verify_integrity()
        print(f"  審計驗證: {v['total_records']} 筆, "
              f"{'OK' if v['valid'] else 'CORRUPTED'}")
        print(f"\n最終盈虧: {self.state.daily_pnl:+,.0f}")


def main():
    parser = argparse.ArgumentParser(description="Shioaji 台股模擬盤")
    parser.add_argument("--symbols", type=str, default="2330")
    parser.add_argument("--strategy", type=str, default="ma_cross", choices=["ma_cross", "rsi"])
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--max-position-pct", type=float, default=0.15)
    args = parser.parse_args()

    strategy = MACrossStrategy() if args.strategy == "ma_cross" else RSIStrategy()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    bot = PaperTradingBot(symbols, strategy, args.interval, args.dry_run,
                           args.initial_cash, args.max_position_pct)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n[INFO] 使用者中斷")


if __name__ == "__main__":
    main()
