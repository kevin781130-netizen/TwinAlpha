from app.domain.models import Market, Side


class ShioajiBridge:
    def __init__(self, simulation=True, api_key="", secret_key="",
                 person_id="", passwd="", ca_path="", ca_passwd=""):
        self.simulation = simulation
        self.api_key = api_key
        self.secret_key = secret_key
        self.person_id = person_id
        self.passwd = passwd
        self.ca_path = ca_path
        self.ca_passwd = ca_passwd
        self.api = None

    def connect(self):
        try:
            import shioaji as sj
        except ImportError:
            raise ImportError("pip install shioaji")

        self.api = sj.Shioaji(simulation=self.simulation)

        if self.simulation:
            self.api.login(
                person_id=self.person_id or "PERSON_ID",
                passwd=self.passwd or "PASSWORD",
            )
        else:
            if not self.api_key or not self.secret_key:
                raise ValueError("實盤模式需要 api_key 和 secret_key")
            self.api.login(api_key=self.api_key, secret_key=self.secret_key)
            if self.ca_path:
                self.api.activate_ca(ca_path=self.ca_path,
                                     ca_passwd=self.ca_passwd,
                                     person_id=self.person_id)
        return self.api

    def place_order(self, symbol, side, price, qty,
                    price_type="LMT", order_type="ROD") -> dict:
        import shioaji as sj
        if self.api is None:
            self.connect()

        contract = None
        for exchange in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC]:
            if symbol in exchange:
                contract = exchange[symbol]
                break

        if contract is None:
            return {"error": f"contract not found: {symbol}"}

        action = sj.constant.Action.Buy if side == Side.BUY else sj.constant.Action.Sell
        order = self.api.Order(
            action=action, price=price, quantity=qty,
            price_type=getattr(sj.constant.StockPriceType, price_type),
            order_type=getattr(sj.constant.TFTOrderType, order_type),
            account=self.api.stock_account,
        )
        trade = self.api.place_order(contract, order)

        return {
            "order_id": str(trade.order.id),
            "symbol": symbol, "side": side.value,
            "price": price, "qty": qty,
            "status": str(trade.status.status),
            "simulation": self.simulation,
        }

    def get_positions(self) -> list[dict]:
        if self.api is None:
            self.connect()
        positions = []
        try:
            for p in self.api.list_positions(self.api.stock_account):
                positions.append({"symbol": p.code, "qty": p.quantity,
                                  "price": p.price, "pnl": p.pnl})
        except Exception as e:
            return [{"error": str(e)}]
        return positions

    def cancel_order(self, order_id: str) -> bool:
        if self.api is None:
            self.connect()
        try:
            self.api.cancel_order(self.api.stock_account, order_id)
            return True
        except Exception:
            return False
