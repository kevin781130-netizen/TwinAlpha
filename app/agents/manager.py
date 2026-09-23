import json

from app.agents.llm import LLMClient
from app.agents.risk import RiskAgent
from app.domain.models import (
    AnalystReport, DebateResult, FinalDecision, Market, RiskReview,
)


class PortfolioManagerAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    async def decide(self, symbol, market, reports, debate, risk) -> FinalDecision:
        if not risk.approved:
            return FinalDecision(
                symbol=symbol, market=market, action="AVOID",
                confidence=0.0, target_position_pct=0.0,
                thesis=f"風控未通過：{risk.notes}",
                reports=reports, debate=debate, risk=risk,
            )

        reports_dump = [
            r.model_dump() if hasattr(r, "model_dump") else r for r in reports
        ]

        prompt = f"""
你是投資組合經理。請根據以下資訊，對 {market.value}:{symbol} 做最終決策。

分析報告：
{json.dumps(reports_dump, ensure_ascii=False, default=str)[:5000]}

多空辯論：
{debate.model_dump_json()[:3000] if hasattr(debate, "model_dump_json") else str(debate)[:3000]}

風控：
{risk.model_dump_json() if hasattr(risk, "model_dump_json") else str(risk)}

請只輸出 JSON：
{{
  "action": "BUY/HOLD/SELL/AVOID",
  "confidence": 0 到 1,
  "target_position_pct": 0 到 1,
  "entry_price": null,
  "stop_loss": null,
  "take_profit": null,
  "thesis": "..."
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return FinalDecision(symbol=symbol, market=market, action="HOLD",
                                 confidence=0.0, target_position_pct=0.0,
                                 thesis=f"LLM 調用失敗: {e}",
                                 reports=reports, debate=debate, risk=risk)

        data = RiskAgent._extract_json(text) or {}
        action = str(data.get("action", "HOLD")).upper()
        if action not in ("BUY", "HOLD", "SELL", "AVOID"):
            action = "HOLD"

        target_pct = min(
            max(float(data.get("target_position_pct", 0.0)), 0.0),
            risk.max_position_pct,
        )

        return FinalDecision(
            symbol=symbol, market=market, action=action,
            confidence=min(max(float(data.get("confidence", 0.5)), 0.0), 1.0),
            target_position_pct=target_pct,
            entry_price=data.get("entry_price"),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            thesis=str(data.get("thesis", text[:500]))[:2000],
            reports=reports, debate=debate, risk=risk,
        )
