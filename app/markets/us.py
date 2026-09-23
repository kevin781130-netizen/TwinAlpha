from app.config import settings
from app.domain.models import Market, Side
from app.markets.base import MarketRules


class USRules(MarketRules):
    market = Market.US
    settlement_days = 1
    price_limit_pct = None
    lot_size = 1

    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        commission = settings.default_us_commission
        sec_fee = (
            price * qty * settings.default_us_sec_fee_rate
            if side == Side.SELL else 0.0
        )
        finra_taf = (
            qty * settings.default_us_finra_taf_per_share
            if side == Side.SELL else 0.0
        )
        finra_taf = min(finra_taf, 8.30)
        return round(commission + sec_fee + finra_taf, 4)

    def price_limits(self, prev_close: float):
        return None, None
