import re

import numpy as np
import pandas as pd


class SignalDSL:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy().reset_index(drop=True)

        for col in ["close", "open", "high", "low", "volume"]:
            if col not in self.df.columns:
                self.df[col] = np.nan

        self.df["returns"] = self.df["close"].pct_change()
        self.df["vwap"] = (
            (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        )

    # ---------- 基礎指標 ----------

    def sma(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def mean(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def ema(self, col, n):
        return self.df[col].ewm(span=int(n), adjust=False).mean()

    def std(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def stdev(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def rsi(self, col, n=14):
        n = int(n)
        delta = self.df[col].diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return 100 - 100 / (1 + rs)

    def atr(self, n=14):
        n = int(n)
        tr = pd.concat([
            self.df["high"] - self.df["low"],
            (self.df["high"] - self.df["close"].shift()).abs(),
            (self.df["low"] - self.df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(n).mean()

    def zscore(self, col, n):
        n = int(n)
        m = self.df[col].rolling(n).mean()
        s = self.df[col].rolling(n).std() + 1e-9
        return (self.df[col] - m) / s

    def highest(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def lowest(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def max(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def min(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def slope(self, col, n):
        n = int(n)

        def _slope(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            return np.polyfit(range(len(x)), x, 1)[0]

        return self.df[col].rolling(n).apply(_slope, raw=True)

    # ---------- 時序函數 ----------

    def delay(self, col, n):
        return self.df[col].shift(int(n))

    def delta(self, col, n):
        return self.df[col].diff(int(n))

    def ts_sum(self, col, n):
        return self.df[col].rolling(int(n)).sum()

    def ts_mean(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def ts_std(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def ts_min(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def ts_max(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def ts_rank(self, col, n):
        n = int(n)

        def _rank(x):
            if len(x) < 2:
                return np.nan
            return (x[:-1] < x[-1]).sum() / (len(x) - 1)

        return self.df[col].rolling(n).apply(_rank, raw=True)

    def ts_argmax(self, col, n):
        n = int(n)
        return self.df[col].rolling(n).apply(
            lambda x: len(x) - 1 - np.argmax(x) if not np.isnan(x).all() else np.nan,
            raw=True,
        )

    def ts_argmin(self, col, n):
        n = int(n)
        return self.df[col].rolling(n).apply(
            lambda x: len(x) - 1 - np.argmin(x) if not np.isnan(x).all() else np.nan,
            raw=True,
        )

    # ---------- 截面函數 ----------

    def rank(self, col):
        return self.df[col].rank(pct=True)

    def sign(self, col):
        return np.sign(self.df[col])

    def abs(self, col):
        return np.abs(self.df[col])

    def log(self, col):
        return np.log(self.df[col].clip(lower=1e-9))

    # ---------- 雙序列 ----------

    def correlation(self, col1, col2, n):
        n = int(n)
        return self.df[col1].rolling(n).corr(self.df[col2])

    def covariance(self, col1, col2, n):
        n = int(n)
        return self.df[col1].rolling(n).cov(self.df[col2])

    # ---------- 分位 ----------

    def quantile(self, col, n, q):
        n = int(n)
        q = float(q)
        return self.df[col].rolling(n).quantile(q)

    # ---------- 其他 ----------

    def signedpower(self, col, power):
        power = float(power)
        return np.sign(self.df[col]) * (np.abs(self.df[col]) ** power)

    def rsquare(self, col, n):
        n = int(n)

        def _r2(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            t = np.arange(len(x))
            corr = np.corrcoef(t, x)[0, 1]
            return corr ** 2 if not np.isnan(corr) else np.nan

        return self.df[col].rolling(n).apply(_r2, raw=True)

    def residual(self, col, n):
        n = int(n)

        def _resid(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            t = np.arange(len(x))
            try:
                slope, intercept = np.polyfit(t, x, 1)
                return x[-1] - (slope * t[-1] + intercept)
            except Exception:
                return np.nan

        return self.df[col].rolling(n).apply(_resid, raw=True)

    # ---------- 表達式求值 ----------

    def evaluate(self, expr: str) -> pd.Series:
        try:
            expr = str(expr).strip()
        except Exception:
            return pd.Series(0, index=self.df.index)

        max_iter = 20
        for _ in range(max_iter):
            m = re.search(r"(\w+)\(([^()]*)\)", expr)
            if not m:
                break

            func = m.group(1)
            args_str = m.group(2)

            parsed = []
            for a in args_str.split(","):
                a = a.strip()
                if not a:
                    continue
                if a in ("close", "open", "high", "low", "volume", "returns", "vwap"):
                    parsed.append(f"'{a}'")
                    continue
                try:
                    parsed.append(str(int(a)))
                    continue
                except ValueError:
                    pass
                try:
                    parsed.append(str(float(a)))
                    continue
                except ValueError:
                    pass
                parsed.append(a)

            replacement = f"__RESULT_{abs(hash(m.group(0))) % 1000000}__"

            if hasattr(self, func):
                try:
                    args_eval = []
                    for p in parsed:
                        if p.startswith("'"):
                            args_eval.append(p.strip("'"))
                        elif p.lstrip("-").isdigit():
                            args_eval.append(int(p))
                        else:
                            try:
                                args_eval.append(float(p))
                            except ValueError:
                                args_eval.append(p)

                    result = getattr(self, func)(*args_eval)
                    if isinstance(result, pd.Series):
                        expr = expr.replace(m.group(0), replacement)
                        if not hasattr(self, "_results"):
                            self._results = {}
                        self._results[replacement] = result
                        continue
                except Exception:
                    pass

            expr = expr.replace(m.group(0), "0")

        for var in ["close", "open", "high", "low", "volume", "returns", "vwap"]:
            expr = re.sub(rf"\b{var}\b", f"self.df['{var}']", expr)

        if hasattr(self, "_results"):
            for key in list(self._results.keys()):
                expr = expr.replace(key, f"self._results['{key}']")

        try:
            result = eval(expr, {"__builtins__": {}},
                          {"self": self, "np": np, "pd": pd})
            if isinstance(result, pd.Series):
                return result
            if isinstance(result, (int, float, np.number)):
                return pd.Series(float(result), index=self.df.index)
        except Exception as e:
            print(f"DSL eval error: {e} | expr={expr}")

        return pd.Series(0, index=self.df.index)

    def discretize(self, score: pd.Series, upper: float = 0.5, lower: float = -0.5) -> pd.Series:
        pos = pd.Series(0, index=score.index)
        pos[score > upper] = 1
        pos[score < lower] = -1
        return pos
