import json
from datetime import datetime

from app.agents.llm import LLMClient
from app.domain.models import Market


def _to_dict(item) -> dict:
    if item is None:
        return {}
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return {"value": str(item)}


class EventDrivenTrader:
    def __init__(self):
        self.llm = LLMClient()

    async def generate_decision(self, symbol, market, structured_data, news_items, portfolio_state) -> dict:
        tech = structured_data.get("technicals", {})
        price = structured_data.get("price", {})
        news_dicts = [_to_dict(n) for n in news_items]

        news_text = "\n".join([
            f"- [{n.get('source', 'unknown')}] {n.get('title', '')}: {str(n.get('summary', ''))[:200]}"
            for n in news_dicts[:10]
        ])

        prompt = f"""
你是事件驅動交易代理。根據以下多模態信息，對 {market.value}:{symbol} 生成交易決策。

=== 結構化市場數據 ===
最新價格: {price.get('last', 'N/A')}
日漲跌幅: {price.get('change_pct', 'N/A')}%
成交量: {price.get('volume', 'N/A')}
RSI(14): {tech.get('RSI', 'N/A')}
MACD: {tech.get('MACD', 'N/A')}
MA20: {tech.get('MA20', 'N/A')}
MA50: {tech.get('MA50', 'N/A')}

=== 非結構化新聞 ===
{news_text}

=== 當前持倉 ===
{json.dumps(portfolio_state, ensure_ascii=False, default=str)[:2000]}

請只輸出 JSON：
{{
  "action": "BUY/HOLD/SELL/AVOID",
  "confidence": 0-1,
  "position_size_pct": 0-0.3,
  "entry_price": 價格或null,
  "stop_loss": 價格或null,
  "take_profit": 價格或null,
  "key_catalyst": "驅動此決策的關鍵事件",
  "news_impact": "POSITIVE/NEGATIVE/NEUTRAL",
  "reasoning": "完整推理過程"
}}
"""
        text = await self.llm.chat([{"role": "user", "content": prompt}])

        try:
            decision = json.loads(text)
        except Exception:
            decision = {"action": "HOLD", "confidence": 0.3,
                        "position_size_pct": 0, "reasoning": text[:500]}

        decision["timestamp"] = datetime.now().isoformat()
        decision["symbol"] = symbol
        decision["market"] = market.value
        return decision

    async def batch_event_scan(self, symbols, market, data_provider):
        results = []
        today = datetime.now().strftime("%Y-%m-%d")

        for sym in symbols:
            try:
                bars = await data_provider.get_bars(sym, market, "2025-01-01", today)
                news = await data_provider.get_news(sym, market, limit=5)

                if bars is None or len(bars) == 0:
                    continue

                close = bars["close"]
                tech = {
                    "RSI": self._calc_rsi(close),
                    "MACD": self._calc_macd(close),
                    "MA20": float(close.rolling(20).mean().iloc[-1]),
                    "MA50": float(close.rolling(50).mean().iloc[-1]),
                }
                structured = {
                    "price": {
                        "last": float(close.iloc[-1]),
                        "change_pct": round(float(close.pct_change().iloc[-1] * 100), 2),
                        "volume": float(bars["volume"].iloc[-1]),
                    },
                    "technicals": tech,
                }

                news_dicts = [_to_dict(n) for n in news]
                decision = await self.generate_decision(sym, market, structured, news_dicts, {})
                results.append(decision)
            except Exception as e:
                results.append({"symbol": sym, "error": str(e)})

        return sorted(results, key=lambda x: x.get("confidence", 0), reverse=True)

    def _calc_rsi(self, close, n=14):
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return round(float(100 - 100 / (1 + rs).iloc[-1]), 2)

    def _calc_macd(self, close):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        return round(float((ema12 - ema26).iloc[-1]), 4)
