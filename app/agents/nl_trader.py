import json
from datetime import datetime

from app.agents.llm import LLMClient
from app.domain.models import Market, Side


class NLTrader:
    def __init__(self):
        self.llm = LLMClient()
        self.audit_log: list[dict] = []

    async def parse_intent(self, text: str, portfolio_context: dict) -> dict:
        prompt = f"""
你是交易意圖解析器。將用戶的自然語言指令轉為結構化訂單意圖。

用戶指令：{text}

當前持倉：
{json.dumps(portfolio_context, ensure_ascii=False, default=str)[:3000]}

請只輸出 JSON：
{{
  "action": "BUY/SELL/HOLD/CANCEL_ALL",
  "symbol": "股票代碼",
  "market": "TW/US",
  "qty": 數量（整數）,
  "order_type": "MKT/LMT",
  "limit_price": 限價（可選）,
  "reasoning": "解析理由"
}}
"""
        response = await self.llm.chat([{"role": "user", "content": prompt}])
        try:
            intent = json.loads(response)
        except Exception:
            intent = {"action": "HOLD", "reasoning": response[:300]}

        intent["portfolio_value"] = portfolio_context.get("portfolio_value", 1_000_000)
        intent["current_position_value"] = portfolio_context.get("current_position_value", 0)
        intent["current_equity"] = portfolio_context.get("current_equity", 1_000_000)

        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "input": text, "intent": intent, "stage": "parsed",
        })
        return intent

    async def execute(self, intent, risk_guard, broker_tw, broker_us, dry_run=True) -> dict:
        action = intent.get("action", "HOLD")

        if action == "HOLD":
            return {"executed": False, "reason": "no action needed"}

        if action == "CANCEL_ALL":
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "CANCEL_ALL", "stage": "executed",
            })
            return {"executed": True, "action": "CANCEL_ALL"}

        check = risk_guard.check_order(
            symbol=intent.get("symbol", ""), side=action,
            qty=intent.get("qty", 0),
            price=intent.get("limit_price", 0) or 0,
            portfolio_value=intent["portfolio_value"],
            current_position_value=intent["current_position_value"],
            current_equity=intent["current_equity"],
        )

        if not check["approved"]:
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "intent": intent, "risk_check": check, "stage": "blocked",
            })
            return {"executed": False, "reason": check["reason"]}

        adjusted_qty = check.get("adjusted_qty", intent.get("qty", 0))

        if dry_run:
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "intent": intent, "adjusted_qty": adjusted_qty, "stage": "dry_run",
            })
            return {"executed": False, "dry_run": True,
                    "intent": intent, "adjusted_qty": adjusted_qty}

        market = Market(intent.get("market", "TW"))
        side = Side(action)

        if market == Market.TW:
            result = broker_tw.place_order(
                intent["symbol"], side, intent.get("limit_price", 0), adjusted_qty,
            )
        else:
            result = broker_us.place_order(
                intent["symbol"], side, adjusted_qty,
                intent.get("order_type", "MKT"), intent.get("limit_price"),
            )

        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "intent": intent, "result": result, "stage": "executed",
        })
        return {"executed": True, "result": result}

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        return self.audit_log[-limit:]
