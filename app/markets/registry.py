from app.domain.models import Market
from app.markets.taiwan import TaiwanRules
from app.markets.us import USRules

RULES = {
    Market.TW: TaiwanRules(),
    Market.US: USRules(),
}


def get_rules(market: Market):
    return RULES[market]
