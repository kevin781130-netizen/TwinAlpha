import json

from app.agents.llm import LLMClient
from app.domain.models import DebateResult, RiskReview


class RiskAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    async def review(self, symbol: str, debate: DebateResult) -> RiskReview:
        prompt = f"""
你是風險控制官。根據以下多空辯論，給出 {symbol} 的風控參數。

多頭：
{(debate.bull_case or "")[:1500]}

空頭：
{(debate.bear_case or "")[:1500]}

請只輸出 JSON：
{{
  "max_position_pct": 0.1,
  "stop_loss_pct": 0.08,
  "take_profit_pct": 0.2,
  "approved": true,
  "notes": "..."
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return RiskReview(max_position_pct=0.05, stop_loss_pct=0.05,
                              take_profit_pct=0.15, approved=False,
                              notes=f"LLM 調用失敗: {e}")

        data = self._extract_json(text)
        if data is None:
            return RiskReview(max_position_pct=0.05, stop_loss_pct=0.05,
                              take_profit_pct=0.15, approved=False,
                              notes=f"無法解析風控輸出: {text[:300]}")

        return RiskReview(
            max_position_pct=min(max(float(data.get("max_position_pct", 0.1)), 0.0), 0.3),
            stop_loss_pct=min(max(float(data.get("stop_loss_pct", 0.08)), 0.01), 0.2),
            take_profit_pct=min(max(float(data.get("take_profit_pct", 0.2)), 0.02), 1.0),
            approved=bool(data.get("approved", False)),
            notes=str(data.get("notes", ""))[:1000],
        )

    @staticmethod
    def _extract_json(text: str):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None
