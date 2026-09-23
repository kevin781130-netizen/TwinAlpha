import pandas as pd
from FinMind.data import DataLoader

from app.config import settings
from app.data.base import DataProvider
from app.data.warehouse import MarketWarehouse
from app.domain.models import Market, NewsItem


class FinMindProvider(DataProvider):
    def __init__(self):
        self.dl = DataLoader()
        if settings.finmind_token:
            try:
                self.dl.login_by_token(api_token=settings.finmind_token)
            except Exception as e:
                print(f"FinMind login failed: {e}")
        self.warehouse = MarketWarehouse()

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ) -> pd.DataFrame:
        if market != Market.TW:
            raise ValueError("FinMindProvider only supports TW")

        cached = self.warehouse.query_bars(symbol, market, start, end)
        if not cached.empty:
            return cached

        try:
            df = self.dl.taiwan_stock_daily(
                stock_id=symbol, start_date=start, end_date=end,
            )
        except Exception as e:
            print(f"FinMind fetch error: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "date": "timestamp",
            "max": "high",
            "min": "low",
            "Trading_Volume": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["symbol"] = symbol
        df["market"] = Market.TW.value

        df = df[["timestamp", "symbol", "market",
                 "open", "high", "low", "close", "volume"]]

        self.warehouse.upsert_bars(df)
        self.warehouse.save_bars_parquet(df, Market.TW.value)
        return df

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        return {}

    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        return []
