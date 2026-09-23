import math

import numpy as np
import pandas as pd
import yfinance as yf

from app.data.warehouse import MarketWarehouse


class USOptionsFactorEngine:
    def __init__(self):
        self.warehouse = MarketWarehouse()

    def fetch_chain(self, symbol: str, max_expiries: int = 4) -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
        except Exception as e:
            print(f"yfinance options error for {symbol}: {e}")
            return pd.DataFrame()

        if not expirations:
            return pd.DataFrame()

        rows = []
        today = pd.Timestamp.today().date()

        for exp in expirations[:max_expiries]:
            try:
                chain = ticker.option_chain(exp)
            except Exception:
                continue

            for opt_type, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                if df is None or df.empty:
                    continue
                d = df[["strike", "volume", "openInterest",
                        "impliedVolatility", "bid", "ask", "lastPrice"]].copy()
                d["option_type"] = opt_type
                d["expiry"] = pd.Timestamp(exp).date()
                d["date"] = today
                d["symbol"] = symbol
                rows.append(d)

        if not rows:
            return pd.DataFrame()

        result = pd.concat(rows, ignore_index=True)
        result = result.rename(columns={
            "openInterest": "open_interest",
            "impliedVolatility": "implied_volatility",
            "lastPrice": "last_price",
        })

        try:
            self.warehouse.upsert_us_options(result)
        except Exception as e:
            print(f"Warehouse upsert failed: {e}")

        return result

    def compute_factors(self, symbol: str, spot: float | None = None) -> dict:
        chain = self.fetch_chain(symbol)
        if chain is None or chain.empty:
            return {}

        if spot is None:
            try:
                spot = float(yf.Ticker(symbol).history(period="1d")["Close"].iloc[-1])
            except Exception:
                return {}

        calls = chain[chain["option_type"] == "CALL"]
        puts = chain[chain["option_type"] == "PUT"]

        factors = {}

        call_vol = calls["volume"].sum()
        put_vol = puts["volume"].sum()
        factors["put_call_volume_ratio"] = (
            float(put_vol / call_vol) if call_vol > 0 else np.nan
        )

        call_oi = calls["open_interest"].sum()
        put_oi = puts["open_interest"].sum()
        factors["put_call_oi_ratio"] = (
            float(put_oi / call_oi) if call_oi > 0 else np.nan
        )

        atm_calls = calls.iloc[(calls["strike"] - spot).abs().argsort()[:5]]
        atm_puts = puts.iloc[(puts["strike"] - spot).abs().argsort()[:5]]
        atm_iv_series = pd.concat([atm_calls, atm_puts])["implied_volatility"]
        factors["atm_iv"] = (
            float(atm_iv_series.mean()) if not atm_iv_series.empty else np.nan
        )

        otm_puts = puts[puts["strike"] < spot * 0.95]
        otm_calls = calls[calls["strike"] > spot * 1.05]
        put_iv = otm_puts["implied_volatility"].mean() if not otm_puts.empty else np.nan
        call_iv = otm_calls["implied_volatility"].mean() if not otm_calls.empty else np.nan
        factors["iv_skew"] = (
            float(put_iv - call_iv)
            if pd.notna(put_iv) and pd.notna(call_iv) else np.nan
        )

        factors["max_pain"] = self._calc_max_pain_vectorized(chain, spot)
        factors["gamma_exposure"] = self._calc_gamma_exposure(chain, spot)

        total_oi = chain["open_interest"].sum()
        factors["oi_concentration"] = (
            float(chain.nlargest(5, "open_interest")["open_interest"].sum() / total_oi)
            if total_oi > 0 else np.nan
        )

        return factors

    def _calc_max_pain_vectorized(self, chain, spot) -> float:
        strikes = chain["strike"].dropna().unique()
        strikes = np.sort(strikes)
        strikes = strikes[(strikes >= 0.7 * spot) & (strikes <= 1.3 * spot)]
        if len(strikes) == 0:
            return np.nan

        calls = chain[chain["option_type"] == "CALL"][["strike", "open_interest"]].dropna()
        puts = chain[chain["option_type"] == "PUT"][["strike", "open_interest"]].dropna()

        call_strikes = calls["strike"].values
        call_oi = calls["open_interest"].values
        put_strikes = puts["strike"].values
        put_oi = puts["open_interest"].values

        call_matrix = np.maximum(strikes[:, None] - call_strikes[None, :], 0) * call_oi[None, :]
        put_matrix = np.maximum(put_strikes[None, :] - strikes[:, None], 0) * put_oi[None, :]
        total_pain = call_matrix.sum(axis=1) + put_matrix.sum(axis=1)
        return float(strikes[int(np.argmin(total_pain))])

    def _calc_gamma_exposure(self, chain, spot, r=0.05) -> float:
        if chain.empty or spot <= 0:
            return 0.0

        def norm_pdf(x):
            return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

        total = 0.0
        valid = chain[(chain["strike"] > spot * 0.8) & (chain["strike"] < spot * 1.2)]

        for _, row in valid.iterrows():
            k = float(row["strike"])
            iv = float(row["implied_volatility"]) if pd.notna(row["implied_volatility"]) else 0.0
            oi = float(row["open_interest"]) if pd.notna(row["open_interest"]) else 0.0
            if iv <= 0 or oi <= 0 or k <= 0:
                continue
            t = 0.25
            try:
                d1 = (math.log(spot / k) + (r + 0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
                gamma = norm_pdf(d1) / (spot * iv * math.sqrt(t))
                total += gamma * oi * 100 * spot ** 2
            except Exception:
                continue

        return float(total)
