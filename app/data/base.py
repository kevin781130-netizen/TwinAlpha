from abc import ABC, abstractmethod

import pandas as pd

from app.domain.models import Market, NewsItem


class DataProvider(ABC):
    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        market: Market,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        ...

    @abstractmethod
    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        ...
