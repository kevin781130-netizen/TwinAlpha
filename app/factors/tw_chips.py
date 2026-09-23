import pandas as pd
from FinMind.data import DataLoader

from app.config import settings
from app.data.warehouse import MarketWarehouse


FOREIGN_ALIASES = ["Foreign_Investor", "Foreign_Investor_Dealer",
                   "外資", "外資及陸資", "外陸資"]
TRUST_ALIASES = ["Investment_Trust", "投信", "投信自營商"]
DEALER_ALIASES = ["Dealer_self", "Dealer_Hedging", "Dealer",
                  "自營商", "自營商自行買賣", "自營商避險"]


class TWChipsFactorEngine:
    def __init__(self):
        self.dl = DataLoader()
        if settings.finmind_token:
            try:
                self.dl.login_by_token(api_token=settings.finmind_token)
            except Exception as e:
                print(f"FinMind login failed: {e}")
        self.warehouse = MarketWarehouse()

    def _safe_fetch(self, method_name: str, **kwargs) -> pd.DataFrame:
        try:
            method = getattr(self.dl, method_name, None)
            if method is None:
                return pd.DataFrame()
            df = method(**kwargs)
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            print(f"FinMind fetch error ({method_name}): {e}")
            return pd.DataFrame()

    def fetch_institutional(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_institutional_investors",
                                stock_id=symbol, start_date=start, end_date=end)

    def fetch_margin(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_margin_purchase_short_sale",
                                stock_id=symbol, start_date=start, end_date=end)

    def fetch_day_trade(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_day_trading",
                                stock_id=symbol, start_date=start, end_date=end)

    @staticmethod
    def _match_alias(name_series, aliases):
        mask = pd.Series(False, index=name_series.index)
        for alias in aliases:
            mask |= name_series.str.contains(alias, na=False, case=False)
        return mask

    def build_chip_table(self, symbol, start, end) -> pd.DataFrame:
        inst = self.fetch_institutional(symbol, start, end)
        margin = self.fetch_margin(symbol, start, end)
        day_trade = self.fetch_day_trade(symbol, start, end)

        rows = []

        if not inst.empty and "date" in inst.columns:
            for date, group in inst.groupby("date"):
                foreign_mask = self._match_alias(group["name"], FOREIGN_ALIASES)
                trust_mask = self._match_alias(group["name"], TRUST_ALIASES)
                dealer_mask = self._match_alias(group["name"], DEALER_ALIASES)

                def _sum(mask, col):
                    if col not in group.columns:
                        return 0.0
                    return float(group.loc[mask, col].sum())

                foreign_buy = _sum(foreign_mask, "buy")
                foreign_sell = _sum(foreign_mask, "sell")
                trust_buy = _sum(trust_mask, "buy")
                trust_sell = _sum(trust_mask, "sell")
                dealer_buy = _sum(dealer_mask, "buy")
                dealer_sell = _sum(dealer_mask, "sell")

                rows.append({
                    "date": date, "symbol": symbol,
                    "foreign_buy": foreign_buy, "foreign_sell": foreign_sell,
                    "foreign_net": foreign_buy - foreign_sell,
                    "trust_buy": trust_buy, "trust_sell": trust_sell,
                    "trust_net": trust_buy - trust_sell,
                    "dealer_net": dealer_buy - dealer_sell,
                    "margin_balance": 0.0, "short_balance": 0.0,
                    "day_trade_volume": 0.0,
                })

        chip = pd.DataFrame(rows)
        if chip.empty:
            return chip

        chip = chip.set_index("date")

        if not margin.empty and "date" in margin.columns:
            margin = margin.set_index("date")
            for col, target in [
                ("MarginPurchaseTodayBalance", "margin_balance"),
                ("MarginPurchaseBalance", "margin_balance"),
                ("ShortSaleTodayBalance", "short_balance"),
                ("ShortSaleBalance", "short_balance"),
            ]:
                if col in margin.columns:
                    chip[target] = margin[col].reindex(chip.index).fillna(0.0)

        if not day_trade.empty and "date" in day_trade.columns:
            dt_col = None
            for col in ["volume", "Volume", "trade_volume", "day_trade_volume"]:
                if col in day_trade.columns:
                    dt_col = col
                    break
            if dt_col:
                dt = day_trade.groupby("date")[dt_col].sum()
                chip["day_trade_volume"] = dt.reindex(chip.index).fillna(0.0)

        chip = chip.reset_index()
        chip["symbol"] = symbol
        chip["date"] = pd.to_datetime(chip["date"])

        try:
            self.warehouse.upsert_tw_chips(chip)
        except Exception as e:
            print(f"Warehouse upsert failed: {e}")

        return chip

    def compute_factors(self, symbol, start, end) -> pd.DataFrame:
        raw = self.warehouse.query_tw_chips(symbol, start, end)
        if raw is None or raw.empty:
            raw = self.build_chip_table(symbol, start, end)
        if raw is None or raw.empty:
            return pd.DataFrame()

        raw = raw.sort_values("date").reset_index(drop=True)
        f = pd.DataFrame()
        f["date"] = raw["date"]

        if "foreign_net" in raw.columns:
            f["foreign_net_5d"] = raw["foreign_net"].rolling(5, min_periods=1).sum()
            f["foreign_net_20d"] = raw["foreign_net"].rolling(20, min_periods=1).sum()

        if "trust_net" in raw.columns:
            f["trust_net_5d"] = raw["trust_net"].rolling(5, min_periods=1).sum()
            f["trust_net_20d"] = raw["trust_net"].rolling(20, min_periods=1).sum()

        if "margin_balance" in raw.columns:
            mb = raw["margin_balance"]
            ma20 = mb.rolling(20, min_periods=1).mean()
            f["margin_ratio"] = mb / (ma20 + 1e-9)

        if "short_balance" in raw.columns and "margin_balance" in raw.columns:
            f["short_margin_ratio"] = raw["short_balance"] / (raw["margin_balance"] + 1e-9)

        if "day_trade_volume" in raw.columns:
            dt = raw["day_trade_volume"]
            f["day_trade_ratio"] = dt / (dt.rolling(20, min_periods=1).mean() + 1e-9)

        if "foreign_net" in raw.columns and "trust_net" in raw.columns:
            combined = raw["foreign_net"] + raw["trust_net"]
            std20 = combined.rolling(20, min_periods=1).std()
            f["chip_concentration"] = combined / (std20 + 1e-9)

        f["symbol"] = symbol
        return f
