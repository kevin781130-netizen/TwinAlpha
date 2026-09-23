import numpy as np
import pandas as pd


class NeutrinoEngine:
    def __init__(self):
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            import numba
            self.numba = numba
            return True
        except ImportError:
            return False

    def vectorized_backtest(
        self, close, signals,
        fee_rate: float = 0.001,
        slippage_pct: float = 0.001,
        initial_capital: float = 1_000_000,
    ) -> dict:
        close = np.asarray(close, dtype=np.float64)
        signals = np.asarray(signals, dtype=np.float64)

        if len(close) != len(signals):
            return {"error": "close and signals must have same length"}

        if self._available:
            return self._backtest_numba(close, signals, fee_rate, slippage_pct, initial_capital)
        return self._backtest_python(close, signals, fee_rate, slippage_pct, initial_capital)

    def _backtest_python(self, close, signals, fee_rate, slippage_pct, initial_capital) -> dict:
        n = len(close)
        cash = float(initial_capital)
        position = 0.0
        equity = np.zeros(n)
        equity[0] = cash
        trades = []
        prev_signal = 0.0

        for i in range(1, n):
            sig = signals[i]
            price = close[i]
            if np.isnan(price) or price <= 0:
                equity[i] = cash + position * (close[i - 1] if i > 0 else 0)
                continue

            if sig != prev_signal:
                if position > 0 and sig <= 0:
                    sell_price = price * (1 - slippage_pct)
                    proceeds = position * sell_price * (1 - fee_rate)
                    cash += proceeds
                    trades.append({"index": i, "side": "SELL",
                                   "price": sell_price, "qty": position})
                    position = 0.0

                if sig > 0 and position <= 0:
                    buy_price = price * (1 + slippage_pct)
                    qty = (cash * 0.95) / buy_price
                    cost = qty * buy_price * (1 + fee_rate)
                    if cost <= cash:
                        cash -= cost
                        position = qty
                        trades.append({"index": i, "side": "BUY",
                                       "price": buy_price, "qty": qty})

            equity[i] = cash + position * price
            prev_signal = sig

        return self._calc_metrics(equity, trades, close)

    def _backtest_numba(self, close, signals, fee_rate, slippage_pct, initial_capital) -> dict:
        @self.numba.njit(cache=True)
        def _kernel(close, signals, fee_rate, slippage_pct, initial_capital):
            n = len(close)
            cash = float(initial_capital)
            position = 0.0
            equity = np.zeros(n)
            equity[0] = cash
            trade_buf = np.zeros((n, 4), dtype=np.float64)
            trade_count = 0
            prev_signal = 0.0

            for i in range(1, n):
                sig = signals[i]
                price = close[i]
                if np.isnan(price) or price <= 0:
                    equity[i] = cash + position * close[i - 1]
                    continue

                if sig != prev_signal:
                    if position > 0 and sig <= 0:
                        sell_price = price * (1 - slippage_pct)
                        proceeds = position * sell_price * (1 - fee_rate)
                        cash += proceeds
                        trade_buf[trade_count, 0] = i
                        trade_buf[trade_count, 1] = -1
                        trade_buf[trade_count, 2] = sell_price
                        trade_buf[trade_count, 3] = position
                        trade_count += 1
                        position = 0.0

                    if sig > 0 and position <= 0:
                        buy_price = price * (1 + slippage_pct)
                        qty = (cash * 0.95) / buy_price
                        cost = qty * buy_price * (1 + fee_rate)
                        if cost <= cash:
                            cash -= cost
                            position = qty
                            trade_buf[trade_count, 0] = i
                            trade_buf[trade_count, 1] = 1
                            trade_buf[trade_count, 2] = buy_price
                            trade_buf[trade_count, 3] = qty
                            trade_count += 1

                equity[i] = cash + position * price
                prev_signal = sig

            return equity, trade_buf[:trade_count]

        equity, trades = _kernel(close, signals, float(fee_rate),
                                 float(slippage_pct), float(initial_capital))

        trade_list = [
            {"index": int(t[0]), "side": "BUY" if t[1] > 0 else "SELL",
             "price": float(t[2]), "qty": float(t[3])}
            for t in trades
        ]
        return self._calc_metrics(equity, trade_list, close)

    def _calc_metrics(self, equity, trades, close) -> dict:
        eq = pd.Series(equity)
        eq = eq[eq > 0]
        if len(eq) < 2:
            return {"error": "insufficient data"}

        returns = eq.pct_change().dropna()
        total_return = float(eq.iloc[-1] / eq.iloc[0] - 1)
        sharpe = float(returns.mean() / (returns.std() + 1e-9) * (252 ** 0.5))
        max_dd = float(((eq / eq.cummax()) - 1).min())

        downside = returns[returns < 0]
        sortino = float(returns.mean() / (downside.std() + 1e-9) * (252 ** 0.5))
        calmar = float(total_return / (abs(max_dd) + 1e-9))

        return {
            "total_return": round(total_return, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "calmar": round(calmar, 4),
            "max_drawdown": round(max_dd, 4),
            "num_trades": len(trades),
            "win_rate": self._calc_win_rate(trades),
        }

    def _calc_win_rate(self, trades) -> float:
        if len(trades) < 2:
            return 0.0
        wins = 0
        pairs = 0
        for i in range(len(trades) - 1):
            t1, t2 = trades[i], trades[i + 1]
            if t1["side"] == "BUY" and t2["side"] == "SELL":
                if t2["price"] > t1["price"]:
                    wins += 1
                pairs += 1
        return round(wins / pairs, 4) if pairs > 0 else 0.0

    def parameter_sweep(self, bars, strategy_fn, param_grid, max_combinations=5000) -> pd.DataFrame:
        import itertools
        import random

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        if len(combinations) > max_combinations:
            random.seed(42)
            combinations = random.sample(combinations, max_combinations)

        close = bars["close"].values
        results = []

        for combo in combinations:
            params = dict(zip(keys, combo))
            try:
                signals = strategy_fn(close, **params)
                metrics = self.vectorized_backtest(close, signals)
                if "error" not in metrics:
                    metrics.update(params)
                    results.append(metrics)
            except Exception:
                continue

        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values("sharpe", ascending=False)
        return df
