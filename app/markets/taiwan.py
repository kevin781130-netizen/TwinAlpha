from app.config import settings
from app.domain.models import Market, Side
from app.markets.base import MarketRules


def _tick_size(price: float) -> float:
    """台股升降單位。"""
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0


class TaiwanRules(MarketRules):
    market = Market.TW
    settlement_days = 2
    price_limit_pct = 0.10
    lot_size = 1

    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        gross = price * qty
        fee = gross * settings.default_tw_fee_rate * settings.default_tw_fee_discount
        fee = max(fee, settings.default_tw_min_fee)
        tax = gross * settings.default_tw_tax_rate_sell if side == Side.SELL else 0.0
        return round(fee + tax, 2)

    def price_limits(self, prev_close: float) -> tuple[float, float]:
        raw_upper = prev_close * (1 + self.price_limit_pct)
        raw_lower = prev_close * (1 - self.price_limit_pct)
        upper = self._ceil_tick(raw_upper)
        lower = self._floor_tick(raw_lower)
        return upper, lower

    @staticmethod
    def _ceil_tick(price: float) -> float:
        import math
        tick = _tick_size(price)
        return round(math.ceil(price / tick) * tick, 4)

    @staticmethod
    def _floor_tick(price: float) -> float:
        import math
        tick = _tick_size(price)
        return round(math.floor(price / tick) * tick, 4)
