from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from app.domain.models import Market, Side


class MarketRules(ABC):
    market: Market
    settlement_days: int
    price_limit_pct: float | None
    lot_size: int = 1

    @abstractmethod
    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        ...

    @abstractmethod
    def price_limits(self, prev_close: float):
        ...

    def settlement_date(self, trade_date: datetime) -> datetime:
        return trade_date + timedelta(days=self.settlement_days)

    def round_lot(self, qty: int) -> int:
        if qty <= 0:
            return 0
        if self.lot_size <= 1:
            return int(qty)
        return (int(qty) // self.lot_size) * self.lot_size

    def can_execute(self, side: Side, price: float, prev_close: float | None) -> bool:
        if self.price_limit_pct is None or prev_close is None or prev_close <= 0:
            return True

        upper, lower = self.price_limits(prev_close)

        if side == Side.BUY and upper is not None and price > upper:
            return False
        if side == Side.SELL and lower is not None and price < lower:
            return False
        return True
