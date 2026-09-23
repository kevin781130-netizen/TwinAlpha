from app.agents.analysts import build_analysts
from app.agents.debate import DebateEngine
from app.agents.event_driven import EventDrivenTrader, _to_dict
from app.agents.manager import PortfolioManagerAgent
from app.agents.risk import RiskAgent
from app.data.composite import CompositeProvider
from app.domain.models import Market


class InvestmentOrchestrator:
    def __init__(self):
        self.data = CompositeProvider()
        self.debate = DebateEngine()
        self.risk = RiskAgent()
        self.manager = PortfolioManagerAgent()
        self.event_trader = EventDrivenTrader()

    async def analyze(self, symbol, market, start, end,
                      use_event_driven=True, use_memory=True) -> dict:
        bars = await self.data.get_bars(symbol, market, start, end)
        fundamentals = await self.data.get_fundamentals(symbol, market)
        news = await self.data.get_news(symbol, market, limit=20)

        context = {
            "bars_tail": (bars.tail(60).to_dict("records")
                          if bars is not None and not bars.empty else []),
            "fundamentals": fundamentals,
            "news": [_to_dict(n) for n in news],
        }

        # 因子層（可選）
        try:
            from app.factors.registry import FactorRegistry
            from app.backtest.signal_dsl import SignalDSL
            if bars is not None and not bars.empty:
                registry = FactorRegistry()
                production = registry.get_production_factors(market.value)
                if production:
                    dsl = SignalDSL(bars)
                    factor_values = {}
                    for f in production[:20]:
                        try:
                            score = dsl.evaluate(f["expr"])
                            factor_values[f["name"]] = float(score.iloc[-1])
                        except Exception:
                            continue
                    context["active_factors"] = factor_values
        except Exception as e:
            context["factor_error"] = str(e)

        # 台股籌碼 / 美股期權（可選）
        try:
            if market == Market.TW and bars is not None and not bars.empty:
                from app.factors.tw_chips import TWChipsFactorEngine
                chips = TWChipsFactorEngine().compute_factors(symbol, start, end)
                if chips is not None and not chips.empty:
                    context["chip_factors"] = chips.tail(20).to_dict("records")
            if market == Market.US:
                from app.factors.us_options import USOptionsFactorEngine
                context["option_factors"] = USOptionsFactorEngine().compute_factors(symbol)
        except Exception as e:
            context["extra_factor_error"] = str(e)

        # 記憶層（可選）
        if use_memory:
            try:
                from app.memory.trade_memory import TradeMemoryLayer
                memory = TradeMemoryLayer()
                context["similar_trades"] = memory.recall_similar_trades(symbol=symbol, limit=5)
                context["discipline_drift"] = memory.get_discipline_drift()
            except Exception as e:
                context["memory_error"] = str(e)

        # 多分析師
        analysts = build_analysts(market)
        reports = []
        for agent in analysts:
            try:
                reports.append(await agent.analyze(symbol, market, context))
            except Exception as e:
                from app.domain.models import AnalystReport
                reports.append(AnalystReport(
                    role=agent.role, symbol=symbol, market=market,
                    summary=f"分析失敗: {e}", score=0.0,
                    key_points=[], risks=[str(e)],
                ))

        # 辯論
        try:
            debate = await self.debate.run(symbol, reports)
        except Exception as e:
            from app.domain.models import DebateResult
            debate = DebateResult(bull_case=f"辯論失敗: {e}", bear_case="", rounds=[])

        # 風控
        try:
            risk = await self.risk.review(symbol, debate)
        except Exception as e:
            from app.domain.models import RiskReview
            risk = RiskReview(max_position_pct=0.1, stop_loss_pct=0.08,
                              take_profit_pct=0.2, approved=False,
                              notes=f"風控失敗: {e}")

        # 事件驅動
        event_decision = None
        if use_event_driven and bars is not None and not bars.empty:
            try:
                structured = self._build_structured(bars)
                event_decision = await self.event_trader.generate_decision(
                    symbol, market, structured,
                    [_to_dict(n) for n in news], {},
                )
                context["event_driven_decision"] = event_decision
            except Exception as e:
                event_decision = {"error": str(e)}

        # 最終決策
        try:
            decision = await self.manager.decide(symbol, market, reports, debate, risk)
        except Exception as e:
            from app.domain.models import FinalDecision
            decision = FinalDecision(
                symbol=symbol, market=market, action="HOLD",
                confidence=0.0, target_position_pct=0.0,
                thesis=f"經理決策失敗: {e}",
                reports=reports, debate=debate, risk=risk,
            )

        result = decision.model_dump() if hasattr(decision, "model_dump") else decision
        result["event_driven"] = event_decision
        return result

    def _build_structured(self, bars) -> dict:
        close = bars["close"]
        return {
            "price": {
                "last": float(close.iloc[-1]),
                "change_pct": round(float(close.pct_change().iloc[-1] * 100), 2),
                "volume": float(bars["volume"].iloc[-1]),
            },
            "technicals": {
                "RSI": self._rsi(close), "MACD": self._macd(close),
                "MA20": float(close.rolling(20).mean().iloc[-1]),
                "MA50": float(close.rolling(50).mean().iloc[-1]),
            },
        }

    def _rsi(self, close, n=14):
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return round(float(100 - 100 / (1 + rs).iloc[-1]), 2)

    def _macd(self, close):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        return round(float((ema12 - ema26).iloc[-1]), 4)
