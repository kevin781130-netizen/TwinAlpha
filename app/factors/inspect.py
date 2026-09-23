import pandas as pd
import numpy as np


class FactorInspector:
    def __init__(self, bars: pd.DataFrame, factors: pd.DataFrame, factor_cols: list[str]):
        self.bars = bars.copy().sort_values("timestamp").reset_index(drop=True)
        self.factors = factors.copy()
        self.factor_cols = factor_cols
        self.fwd_ret = self.bars["close"].pct_change().shift(-1)

    def compute_ic(self, period: int = 1) -> pd.DataFrame:
        results = []
        fwd = self.bars["close"].pct_change(period).shift(-period)

        for col in self.factor_cols:
            if col not in self.factors.columns:
                continue
            f = self.factors[col].reindex(self.bars.index)
            valid = f.notna() & fwd.notna()
            if valid.sum() < 20:
                continue
            ic = f[valid].corr(fwd[valid])
            rank_ic = f[valid].rank().corr(fwd[valid].rank())
            results.append({
                "factor": col, "IC": round(ic, 6),
                "Rank_IC": round(rank_ic, 6),
                "ICIR": round(ic / (f.std() + 1e-9), 4), "period": period,
            })
        return pd.DataFrame(results)

    def layer_returns(self, factor_col: str, n_layers: int = 5) -> pd.DataFrame:
        f = self.factors[factor_col].reindex(self.bars.index)
        try:
            layers = pd.qcut(f, n_layers, labels=False, duplicates="drop")
        except Exception:
            return pd.DataFrame()

        results = []
        for layer in range(n_layers):
            mask = layers == layer
            ret = self.fwd_ret[mask].mean()
            results.append({"layer": layer + 1,
                            "mean_return": round(ret, 6),
                            "count": int(mask.sum())})
        return pd.DataFrame(results)

    def factor_decay(self, factor_col: str, max_period: int = 20) -> pd.DataFrame:
        f = self.factors[factor_col].reindex(self.bars.index)
        results = []
        for p in range(1, max_period + 1):
            fwd = self.bars["close"].pct_change(p).shift(-p)
            valid = f.notna() & fwd.notna()
            if valid.sum() < 20:
                continue
            ic = f[valid].corr(fwd[valid])
            results.append({"period": p, "IC": round(ic, 6)})
        return pd.DataFrame(results)

    def full_report(self, factor_col: str) -> dict:
        return {
            "ic": self.compute_ic(1).to_dict("records"),
            "ic_5d": self.compute_ic(5).to_dict("records"),
            "ic_20d": self.compute_ic(20).to_dict("records"),
            "layers": self.layer_returns(factor_col).to_dict("records"),
            "decay": self.factor_decay(factor_col).to_dict("records"),
        }
