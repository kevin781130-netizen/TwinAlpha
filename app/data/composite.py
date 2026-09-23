from app.data.base import DataProvider
from app.data.finmind_provider import FinMindProvider
from app.data.yfinance_provider import YFinanceProvider
from app.domain.models import Market, NewsItem


class CompositeProvider(DataProvider):
    def __init__(self):
        self.tw = FinMindProvider()
        self.us = YFinanceProvider()

    def _pick(self, market: Market) -> DataProvider:
        if market == Market.TW:
            return self.tw
        if market == Market.US:
            return self.us
        raise ValueError(f"Unsupported market: {market}")

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ):
        return await self._pick(market).get_bars(symbol, market, start, end, interval)

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        return await self._pick(market).get_fundamentals(symbol, market)

    async def get_news(
        self, symbol: str, market: Market, limit: int = 20,
    ) -> list[NewsItem]:
        return await self._pick(market).get_news(symbol, market, limit)
