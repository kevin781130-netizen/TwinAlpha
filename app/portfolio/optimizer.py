import numpy as np
import pandas as pd

from app.data.warehouse import MarketWarehouse


class PortfolioOptimizer:
    def __init__(self):
        self.warehouse = MarketWarehouse()
        self._skfolio_available = self._check_skfolio()

    def _check_skfolio(self) -> bool:
        try:
            import skfolio  # noqa: F401
            return True
        except ImportError:
            return False

    def load_returns(self, symbols, market, start, end) -> pd.DataFrame:
        frames = {}
        for sym in symbols:
            bars = self.warehouse.query_bars(sym, market, start, end)
            if bars is None or bars.empty:
                continue
            bars = bars.set_index("timestamp").sort_index()
            frames[sym] = bars["close"].pct_change()
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).dropna(how="all").fillna(0)

    def optimize(self, returns, method="hrp", risk_measure="cvar", max_weight=0.3) -> dict:
        if returns.empty or len(returns.columns) < 2:
            return {"error": "need at least 2 assets"}
        if self._skfolio_available:
            try:
                return self._optimize_skfolio(returns, method, risk_measure, max_weight)
            except Exception as e:
                print(f"skfolio failed, fallback to numpy: {e}")
        return self._optimize_numpy(returns, method, max_weight)

    def _optimize_skfolio(self, returns, method, risk_measure, max_weight) -> dict:
        from skfolio.optimization import (
            MeanRisk, HierarchicalRiskParity, RiskBudgeting, MaximumDiversification,
        )
        from skfolio.risk_measures import CVaR, Variance

        if method == "hrp":
            model = HierarchicalRiskParity()
        elif method == "risk_budgeting":
            model = RiskBudgeting()
        elif method == "max_diversification":
            model = MaximumDiversification()
        elif method == "mean_risk":
            rm = CVaR() if risk_measure == "cvar" else Variance()
            model = MeanRisk(risk_measure=rm, max_weights=max_weight)
        else:
            model = HierarchicalRiskParity()

        model.fit(returns)
        weights = np.asarray(model.weights_)
        return self._summarize(returns, weights, method)

    def _optimize_numpy(self, returns, method, max_weight) -> dict:
        n = len(returns.columns)
        if method == "hrp":
            weights = self._hrp_numpy(returns)
        elif method == "risk_budgeting":
            weights = self._risk_parity_numpy(returns)
        elif method == "max_diversification":
            weights = self._max_div_numpy(returns)
        else:
            weights = self._equal_weight(n)

        weights = np.minimum(weights, max_weight)
        weights = weights / (weights.sum() + 1e-9)
        return self._summarize(returns, weights, f"{method}_numpy")

    def _hrp_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        n = cov.shape[0]
        std = np.sqrt(np.diag(cov))
        corr = cov / (np.outer(std, std) + 1e-9)
        dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))

        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform

        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="single")
        order = leaves_list(link)

        weights = np.ones(n)
        clusters = [list(order)]

        while clusters:
            new_clusters = []
            for cluster in clusters:
                if len(cluster) <= 1:
                    continue
                mid = len(cluster) // 2
                left, right = cluster[:mid], cluster[mid:]

                var_left = self._cluster_var(cov, left)
                var_right = self._cluster_var(cov, right)
                total = var_left + var_right + 1e-9
                alpha = 1 - var_left / total

                for i in left:
                    weights[i] *= alpha
                for i in right:
                    weights[i] *= (1 - alpha)

                new_clusters.extend([left, right])
            clusters = new_clusters

        return weights / (weights.sum() + 1e-9)

    def _cluster_var(self, cov, indices) -> float:
        sub = cov[np.ix_(indices, indices)]
        w = np.ones(len(indices)) / len(indices)
        return float(w @ sub @ w)

    def _risk_parity_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        n = cov.shape[0]
        w = np.ones(n) / n

        for _ in range(200):
            marginal = cov @ w
            rc = w * marginal
            target = rc.mean()
            w = w * (target / (rc + 1e-9))
            w = w / (w.sum() + 1e-9)
        return w

    def _max_div_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        vols = np.sqrt(np.diag(cov))
        inv_vol = 1 / (vols + 1e-9)
        w = inv_vol / inv_vol.sum()

        for _ in range(50):
            marginal = cov @ w
            grad = vols / (np.sqrt(w @ cov @ w) + 1e-9) - marginal
            w = w + 0.01 * grad
            w = np.maximum(w, 1e-6)
            w = w / w.sum()
        return w

    def _equal_weight(self, n) -> np.ndarray:
        return np.ones(n) / n

    def _summarize(self, returns, weights, method) -> dict:
        portfolio_ret = (returns * weights).sum(axis=1)
        cum_ret = (1 + portfolio_ret).cumprod()

        sharpe = float(portfolio_ret.mean() / (portfolio_ret.std() + 1e-9) * (252 ** 0.5))
        max_dd = float(((cum_ret / cum_ret.cummax()) - 1).min())

        return {
            "method": method,
            "weights": {col: round(float(w), 4)
                        for col, w in zip(returns.columns, weights)},
            "metrics": {
                "sharpe": round(sharpe, 4),
                "total_return": round(float(cum_ret.iloc[-1] - 1), 4),
                "max_drawdown": round(max_dd, 4),
                "annual_volatility": round(float(portfolio_ret.std() * (252 ** 0.5)), 4),
            },
        }
