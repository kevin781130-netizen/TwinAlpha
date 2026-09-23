import numpy as np
import pandas as pd
from itertools import combinations


class WalkForwardEngine:
    def __init__(
        self,
        train_window: int = 252,
        test_window: int = 63,
        step: int = 63,
        n_splits: int = 10,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.n_splits = n_splits

    def walk_forward(self, bars, signal_fn, backtest_fn) -> dict:
        df = bars.copy().reset_index(drop=True)
        n = len(df)
        results = []

        start = 0
        while start + self.train_window + self.test_window <= n:
            train = df.iloc[start : start + self.train_window]
            test = df.iloc[
                start + self.train_window :
                start + self.train_window + self.test_window
            ]

            signal_gen = signal_fn(train)
            signals = signal_gen(test)

            result = backtest_fn(test, signals)
            result["window"] = {
                "train_start": str(train["timestamp"].iloc[0]),
                "train_end": str(train["timestamp"].iloc[-1]),
                "test_start": str(test["timestamp"].iloc[0]),
                "test_end": str(test["timestamp"].iloc[-1]),
            }
            results.append(result)
            start += self.step

        all_trades = []
        all_equity = []
        for i, r in enumerate(results):
            for t in r.get("trades", []):
                t["window_idx"] = i
                all_trades.append(t)
            for e in r.get("equity_curve", []):
                e["window_idx"] = i
                all_equity.append(e)

        return {
            "windows": results,
            "summary": self._summarize(results),
            "all_trades": all_trades,
            "all_equity": all_equity,
        }

    def _summarize(self, results) -> dict:
        sharpes, returns, drawdowns = [], [], []

        for r in results:
            eq = pd.DataFrame(r.get("equity_curve", []))
            if eq.empty:
                continue
            eq["return"] = eq["equity"].pct_change()
            sharpe = eq["return"].mean() / (eq["return"].std() + 1e-9) * (252 ** 0.5)
            total_ret = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
            max_dd = ((eq["equity"] / eq["equity"].cummax()) - 1).min()
            sharpes.append(sharpe)
            returns.append(total_ret)
            drawdowns.append(max_dd)

        if not sharpes:
            return {}

        return {
            "num_windows": len(sharpes),
            "sharpe_mean": round(float(np.mean(sharpes)), 4),
            "sharpe_std": round(float(np.std(sharpes)), 4),
            "sharpe_min": round(float(np.min(sharpes)), 4),
            "sharpe_max": round(float(np.max(sharpes)), 4),
            "return_mean": round(float(np.mean(returns)), 4),
            "return_win_rate": round(sum(1 for r in returns if r > 0) / len(returns), 4),
            "max_drawdown_mean": round(float(np.mean(drawdowns)), 4),
            "oos_consistency": round(
                float(np.mean(sharpes)) / (float(np.std(sharpes)) + 1e-9), 4
            ),
        }

    def cscv(self, bars, signal_candidates, backtest_fn) -> dict:
        n = len(bars)
        split_size = n // self.n_splits
        if split_size < 10:
            return {"error": "not enough data for CSCV"}

        splits = []
        for i in range(self.n_splits):
            start = i * split_size
            end = start + split_size
            splits.append(bars.iloc[start:end].copy())

        perf_matrix = {}
        for name, sig_fn in signal_candidates.items():
            perfs = []
            for s in splits:
                signals = sig_fn(s)
                result = backtest_fn(s, signals)
                eq = pd.DataFrame(result.get("equity_curve", []))
                if eq.empty:
                    perfs.append(0)
                    continue
                eq["return"] = eq["equity"].pct_change()
                sharpe = eq["return"].mean() / (eq["return"].std() + 1e-9) * (252 ** 0.5)
                perfs.append(sharpe)
            perf_matrix[name] = perfs

        n_comb = self.n_splits // 2
        combo_indices = list(combinations(range(self.n_splits), n_comb))
        n_combos = len(combo_indices)

        if n_combos > 5000:
            idx = np.random.choice(n_combos, 5000, replace=False)
            combo_indices = [combo_indices[i] for i in idx]

        logits = []
        for combo in combo_indices:
            is_idx = list(combo)
            oos_idx = [i for i in range(self.n_splits) if i not in combo]

            is_perf = {name: np.mean([perfs[i] for i in is_idx])
                       for name, perfs in perf_matrix.items()}
            oos_perf = {name: np.mean([perfs[i] for i in oos_idx])
                        for name, perfs in perf_matrix.items()}

            best_is = max(is_perf, key=is_perf.get)
            rank_oos = sorted(oos_perf, key=oos_perf.get, reverse=True)
            rank = rank_oos.index(best_is) + 1

            omega = rank / (len(rank_oos) + 1)
            logit = np.log(omega / (1 - omega + 1e-9))
            logits.append(logit)

        pbo = sum(1 for l in logits if l <= 0) / len(logits)

        return {
            "PBO": round(pbo, 4),
            "interpretation": (
                "低過擬合風險" if pbo < 0.2
                else "中等過擬合風險" if pbo < 0.5
                else "高過擬合風險"
            ),
            "num_combinations": len(logits),
            "perf_matrix": perf_matrix,
        }
