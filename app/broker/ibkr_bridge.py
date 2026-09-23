from app.domain.models import Side


class IBKRBridge:
    def __init__(self, host="127.0.0.1", port=4002, client_id=1, paper=True):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.paper = paper
        self.ib = None

    def connect(self):
        try:
            from ib_insync import IB
        except ImportError:
            raise ImportError("pip install ib_insync")

        self.ib = IB()
        self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
        return self.ib

    def disconnect(self):
        if self.ib is not None and self.ib.isConnected():
            self.ib.disconnect()

    def place_order(self, symbol, side, qty, order_type="MKT", limit_price=None) -> dict:
        from ib_insync import Stock, MarketOrder, LimitOrder
        if self.ib is None or not self.ib.isConnected():
            self.connect()

        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)

        if order_type == "LMT" and limit_price:
            order = LimitOrder(side.value, qty, limit_price)
        else:
            order = MarketOrder(side.value, qty)

        trade = self.ib.placeOrder(contract, order)
        return {
            "order_id": trade.order.orderId,
            "symbol": symbol, "side": side.value, "qty": qty,
            "order_type": order_type,
            "status": trade.orderStatus.status,
            "paper": self.paper,
        }

    def get_positions(self) -> list[dict]:
        if self.ib is None or not self.ib.isConnected():
            self.connect()
        return [
            {"symbol": p.contract.symbol,
             "qty": float(p.position),
             "avg_cost": float(p.avgCost)}
            for p in self.ib.positions()
        ]

    def cancel_order(self, order_id: int) -> bool:
        if self.ib is None or not self.ib.isConnected():
            self.connect()
        for trade in self.ib.trades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                return True
        return False
