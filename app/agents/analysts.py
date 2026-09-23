import json

from app.agents.llm import LLMClient
from app.domain.models import AnalystReport, Market


class AnalystAgent:
    def __init__(self, role: str, system_prompt: str, llm: LLMClient | None = None):
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm or LLMClient()

    async def analyze(self, symbol: str, market: Market, context: dict) -> AnalystReport:
        prompt = f"""
你是{self.role}。請分析 {market.value} 市場股票 {symbol}。

上下文數據：
{json.dumps(context, ensure_ascii=False, default=str)[:6000]}

請只輸出 JSON：
{{
  "summary": "一段話結論",
  "score": -1 到 1,
  "key_points": ["..."],
  "risks": ["..."]
}}
"""
        text = await self.llm.chat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ])

        data = self._extract_json(text) or {
            "summary": text[:500], "score": 0,
            "key_points": [], "risks": [],
        }

        return AnalystReport(
            role=self.role, symbol=symbol, market=market,
            summary=data.get("summary", "")[:1000],
            score=float(data.get("score", 0)),
            key_points=data.get("key_points", [])[:10],
            risks=data.get("risks", [])[:10],
        )

    @staticmethod
    def _extract_json(text):
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


def build_analysts(market: Market) -> list[AnalystAgent]:
    analysts = [
        AnalystAgent("技術面分析師", "你擅長價量、趨勢、支撐壓力、動量與波動率。"),
        AnalystAgent("基本面分析師", "你擅長財報、估值、成長性、自由現金流與護城河。"),
        AnalystAgent("新聞情緒分析師", "你擅長新聞、社群情緒、事件驅動與市場敘事。"),
    ]

    if market == Market.TW:
        analysts += [
            AnalystAgent("三大法人籌碼分析師", "你專注外資、投信、自營商買賣超、融資融券與持股變化。"),
            AnalystAgent("當沖與量能分析師", "你分析當沖熱度、周轉率、隔日沖風險與量能結構。"),
        ]
    else:
        analysts += [
            AnalystAgent("期權市場分析師", "你分析 Put/Call Ratio、隱含波動率、期權持倉與市場預期。"),
            AnalystAgent("財報事件分析師", "你分析財報日曆、Earnings Surprise、指引變化與事件風險。"),
        ]
    return analysts
