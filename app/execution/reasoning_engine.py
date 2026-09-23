import json

import numpy as np
import pandas as pd

from app.agents.llm import LLMClient


class ReasoningEngine:
    def __init__(self):
        self.llm = LLMClient()

    async def filter_order(self, symbol, side, qty, price, market_context, risk_state) -> dict:
        prompt = f"""
你是執行層推理引擎。判斷以下訂單是否應該執行。

訂單：{side} {symbol} x{qty} @ {price}
市場狀態：{market_context.get('regime', 'unknown')}
當前回撤：{risk_state.get('current_drawdown', 0):.2%}
單日盈虧：{risk_state.get('daily_pnl', 0):.2%}

請只輸出 JSON：
{{
  "decision": "APPROVE/REJECT/MODIFY",
  "reason": "理由",
  "adjusted_qty": 數量,
  "urgency": "HIGH/MEDIUM/LOW"
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return {"decision": "APPROVE", "reason": f"LLM 失敗，默認通過: {e}",
                    "adjusted_qty": qty, "urgency": "MEDIUM"}

        data = self._extract_json(text)
        if data is None:
            return {"decision": "APPROVE", "reason": f"解析失敗，默認通過: {text[:200]}",
                    "adjusted_qty": qty, "urgency": "MEDIUM"}

        if "adjusted_qty" not in data:
            data["adjusted_qty"] = qty
        return data

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


class MarketRegimeDetector:
    @staticmethod
    def detect(bars: pd.DataFrame, lookback: int = 60) -> dict:
        if bars is None or bars.empty or len(bars) < lookback:
            return {"regime": "unknown", "volatility": 0.0,
                    "trend": 0.0, "recommended_position_scale": 0.5}

        close = bars["close"].tail(lookback)
        returns = close.pct_change().dropna()

        vol = float(returns.std() * np.sqrt(252))
        vol_median = float(returns.rolling(max(lookback // 2, 2)).std().median() * np.sqrt(252))

        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
        trend = float((ma20 - ma60) / (ma60 + 1e-9))

        is_high_vol = vol > vol_median * 1.3 if vol_median > 0 else False

        if abs(trend) < 0.02:
            regime = "sideways"
        elif trend > 0:
            regime = "high_vol_bull" if is_high_vol else "low_vol_bull"
        else:
            regime = "high_vol_bear" if is_high_vol else "low_vol_bear"

        return {
            "regime": regime,
            "volatility": round(vol, 4),
            "trend": round(trend, 4),
            "recommended_position_scale": (
                0.5 if "high_vol" in regime
                else 0.7 if regime == "sideways"
                else 1.0
            ),
        }
