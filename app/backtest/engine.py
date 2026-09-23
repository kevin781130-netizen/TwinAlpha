import pandas as pd

from app.domain.models import Market, Side
from app.markets.registry import get_rules


class BacktestEngine:
    def __init__(
        self,
        market: Market,
        initial_cash: float = 1_000_000.0,
        slippage_pct: float = 0.001,
        position_pct: float = 0.1,
        risk_guard=None,
    ):
        self.market = market
        self.rules = get_rules(market)
        self.initial_cash = initial_cash
        self.slippage_pct = slippage_pct
        self.position_pct = position_pct
        self.risk_guard = risk_guard

        self.cash = initial_cash
        self.receivable: list[tuple] = []
        self.positions: dict[str, int] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []

    def _settle(self, current_date):
        remaining = []
        for settle_date, amount in self.receivable:
            if current_date >= settle_date:
                self.cash += amount
            else:
                remaining.append((settle_date, amount))
        self.receivable = remaining

    def _calc_equity(self, current_price: float) -> float:
        receivable_amount = sum(amount for _, amount in self.receivable)
        position_value = sum(
            qty * current_price for qty in self.positions.values()
        )
        return self.cash + receivable_amount + position_value

    def run(self, bars: pd.DataFrame, signals: pd.Series) -> dict:
        if bars is None or bars.empty:
            return {"trades": [], "equity_curve": [], "final_cash": self.cash,
                    "positions": {}, "metrics": {}}

        df = bars.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "UNKNOWN"
        prev_close = None

        if self.risk_guard is not None:
            self.risk_guard.update_equity(self.cash)
            self.risk_guard.reset_daily(self.cash)

        for i, row in df.iterrows():
            current_date = row["timestamp"]
            self._settle(current_date)

            signal = float(signals.iloc[i]) if i < len(signals) else 0.0
            price = float(row["close"])

            if pd.isna(price) or price <= 0:
                equity = self._calc_equity(price if not pd.isna(price) else 0)
                self.equity_curve.append({
                    "date": current_date, "equity": equity,
                    "cash": self.cash,
                    "receivable": sum(a for _, a in self.receivable),
                })
                continue

            equity = self._calc_equity(price)

            if self.risk_guard is not None:
                self.risk_guard.update_equity(equity)

            if signal > 0 and prev_close is not None:
                if self.rules.can_execute(Side.BUY, price, prev_close):
                    target_value = equity * self.position_pct
                    qty = self.rules.round_lot(int(target_value / price)) if price > 0 else 0

                    if qty > 0:
                        if self.risk_guard is not None:
                            check = self.risk_guard.check_order(
                                symbol, "BUY", qty, price,
                                portfolio_value=equity,
                                current_position_value=self.positions.get(symbol, 0) * price,
                                current_equity=equity,
                            )
                            if not check["approved"]:
                                qty = 0
                            else:
                                qty = check.get("adjusted_qty", qty)

                        if qty > 0:
                            buy_price = price * (1 + self.slippage_pct)
                            fee = self.rules.calc_fees(Side.BUY, buy_price, qty)
                            cost = buy_price * qty + fee
                            if cost <= self.cash:
                                self.cash -= cost
                                self.positions[symbol] = self.positions.get(symbol, 0) + qty
                                self.trades.append({
                                    "date": current_date, "side": "BUY",
                                    "price": buy_price, "qty": qty, "fee": fee,
                                })

            elif signal < 0 and self.positions.get(symbol, 0) > 0:
                if prev_close is not None and self.rules.can_execute(Side.SELL, price, prev_close):
                    qty = self.positions[symbol]

                    if self.risk_guard is not None:
                        check = self.risk_guard.check_order(
                            symbol, "SELL", qty, price,
                            portfolio_value=equity,
                            current_position_value=qty * price,
                            current_equity=equity,
                        )
                        if not check["approved"]:
                            qty = 0

                    if qty > 0:
                        sell_price = price * (1 - self.slippage_pct)
                        fee = self.rules.calc_fees(Side.SELL, sell_price, qty)
                        proceeds = sell_price * qty - fee
                        settle_date = self.rules.settlement_date(current_date)

                        self.receivable.append((settle_date, proceeds))
                        self.positions[symbol] = 0
                        self.trades.append({
                            "date": current_date, "side": "SELL",
                            "price": sell_price, "qty": qty, "fee": fee,
                            "settle_date": settle_date,
                        })

            prev_close = price

            equity = self._calc_equity(price)
            self.equity_curve.append({
                "date": current_date, "equity": equity,
                "cash": self.cash,
                "receivable": sum(a for _, a in self.receivable),
            })

        return {
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "final_cash": self.cash,
            "positions": self.positions,
        }
