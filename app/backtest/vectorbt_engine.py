import numpy as np
import pandas as pd


class VectorBTEngine:
    def __init__(self):
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            import vectorbt as vbt
            self.vbt = vbt
            return True
        except ImportError:
            return False

    def ma_cross_sweep(self, close, fast_range, slow_range,
                       fees=0.001425, slippage=0.001) -> pd.DataFrame:
        if not self._available:
            return pd.DataFrame({"error": ["vectorbt not installed"]})

        fast_ma = self.vbt.MA.run(close, window=fast_range)
        slow_ma = self.vbt.MA.run(close, window=slow_range)

        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)

        pf = self.vbt.Portfolio.from_signals(
            close, entries, exits, fees=fees, slippage=slippage, freq="1D",
        )

        return pd.DataFrame({
            "total_return": pf.total_return(),
            "sharpe": pf.sharpe_ratio(),
            "max_drawdown": pf.max_drawdown(),
            "win_rate": pf.trades.win_rate(),
            "num_trades": pf.trades.count(),
        }).sort_values("sharpe", ascending=False)

    def multi_asset_portfolio(self, close_matrix, signals, fees=0.001425) -> dict:
        if not self._available:
            return {"error": "vectorbt not installed"}

        entries = signals == 1
        exits = signals == -1

        pf = self.vbt.Portfolio.from_signals(
            close_matrix, entries, exits, fees=fees, freq="1D",
        )

        return {
            "total_return": float(pf.total_return()),
            "sharpe": float(pf.sharpe_ratio()),
            "max_drawdown": float(pf.max_drawdown()),
            "per_asset": {
                col: {
                    "return": float(pf[col].total_return()),
                    "sharpe": float(pf[col].sharpe_ratio()),
                }
                for col in close_matrix.columns
            },
        }
