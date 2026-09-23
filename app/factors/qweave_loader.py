class QweaveFactorLoader:
    ALPHA101_SUBSET = {
        "alpha001": "ts_argmax(signedpower(returns, 2), 5) - 0.5",
        "alpha002": "-1 * correlation(rank(delta(log(volume), 2)), rank(delta(close, 1)), 6)",
        "alpha003": "-1 * correlation(rank(open), rank(volume), 10)",
        "alpha004": "-1 * ts_rank(rank(low), 9)",
        "alpha006": "-1 * correlation(open, volume, 10)",
        "alpha012": "sign(delta(volume, 1)) * (-1 * delta(close, 1))",
        "alpha014": "(-1 * rank(delta(returns, 3))) * correlation(open, volume, 10)",
        "alpha020": "(-1 * rank(delta(delay(close, 1), 1))) * rank(open) * rank(volume)",
    }

    ALPHA158_SUBSET = {
        "ROC5": "close / delay(close, 5) - 1",
        "ROC10": "close / delay(close, 10) - 1",
        "ROC20": "close / delay(close, 20) - 1",
        "MA5": "mean(close, 5) / close - 1",
        "MA10": "mean(close, 10) / close - 1",
        "STD5": "std(close, 5) / close",
        "STD20": "std(close, 20) / close",
        "BETA5": "slope(close, 5) / close",
        "RSQR5": "rsquare(close, 5)",
        "RESI5": "residual(close, 5)",
        "MAX5": "max(high, 5) / close - 1",
        "MIN5": "min(low, 5) / close - 1",
        "QTLU5": "quantile(close, 5, 0.8) / close - 1",
        "QTLD5": "quantile(close, 5, 0.2) / close - 1",
        "TSRANK5": "ts_rank(close, 5)",
    }

    ALPHA191_SUBSET = {
        "gtja001": "-1 * correlation(rank(delta(log(volume), 1)), rank(delta(close, 1)), 6)",
        "gtja002": "-1 * delta(close, 1)",
        "gtja004": "-1 * ts_rank(rank(low), 9)",
    }

    @classmethod
    def get_all_expressions(cls):
        all_factors = {}
        all_factors.update(cls.ALPHA101_SUBSET)
        all_factors.update(cls.ALPHA158_SUBSET)
        all_factors.update(cls.ALPHA191_SUBSET)
        return all_factors

    @classmethod
    def get_by_category(cls, category):
        if category == "alpha101":
            return cls.ALPHA101_SUBSET
        if category == "alpha158":
            return cls.ALPHA158_SUBSET
        if category == "alpha191":
            return cls.ALPHA191_SUBSET
        return {}

    @classmethod
    def batch_evaluate(cls, bars, categories=None):
        from app.backtest.signal_dsl import SignalDSL
        if categories is None:
            categories = ["alpha101", "alpha158", "alpha191"]

        dsl = SignalDSL(bars)
        results = {}

        for cat in categories:
            factors = cls.get_by_category(cat)
            for name, expr in factors.items():
                try:
                    score = dsl.evaluate(expr)
                    if score.abs().sum() > 1e-9:
                        val = score.iloc[-1]
                        if not (isinstance(val, float) and val != val):
                            results[name] = float(val)
                except Exception as e:
                    print(f"qweave factor {name} failed: {e}")
        return results

    @classmethod
    def batch_evaluate_series(cls, bars, categories=None):
        from app.backtest.signal_dsl import SignalDSL
        if categories is None:
            categories = ["alpha101", "alpha158", "alpha191"]

        dsl = SignalDSL(bars)
        results = {}

        for cat in categories:
            factors = cls.get_by_category(cat)
            for name, expr in factors.items():
                try:
                    score = dsl.evaluate(expr)
                    if score.abs().sum() > 1e-9:
                        results[name] = score
                except Exception as e:
                    print(f"qweave factor {name} failed: {e}")
        return results
