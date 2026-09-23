import pandas as pd
import yfinance as yf

from app.data.base import DataProvider
from app.data.warehouse import MarketWarehouse
from app.domain.models import Market, NewsItem


class YFinanceProvider(DataProvider):
    def __init__(self):
        self.warehouse = MarketWarehouse()

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ) -> pd.DataFrame:
        cached = self.warehouse.query_bars(symbol, market, start, end)
        if not cached.empty:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end,
                                interval=interval, auto_adjust=False)
        except Exception as e:
            print(f"yfinance fetch error: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "timestamp", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df["symbol"] = symbol
        df["market"] = Market.US.value

        df = df[["timestamp", "symbol", "market",
                 "open", "high", "low", "close", "volume"]]

        self.warehouse.upsert_bars(df)
        self.warehouse.save_bars_parquet(df, Market.US.value)
        return df

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        try:
            info = yf.Ticker(symbol).info
            return info or {}
        except Exception:
            return {}

    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        try:
            raw = yf.Ticker(symbol).news or []
        except Exception:
            return []

        out = []
        for item in raw[:limit]:
            published_at = None
            if item.get("providerPublishTime"):
                published_at = pd.to_datetime(item["providerPublishTime"], unit="s")

            out.append(NewsItem(
                title=item.get("title", ""),
                summary=item.get("summary"),
                url=item.get("link"),
                published_at=published_at,
                source=item.get("publisher"),
            ))
        return out
