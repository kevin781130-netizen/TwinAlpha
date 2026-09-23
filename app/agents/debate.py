from app.agents.llm import LLMClient
from app.domain.models import AnalystReport, DebateResult


class DebateEngine:
    def __init__(self, llm: LLMClient | None = None, n_rounds: int = 2):
        self.llm = llm or LLMClient()
        self.n_rounds = max(1, int(n_rounds))

    async def run(self, symbol: str, reports: list[AnalystReport]) -> DebateResult:
        report_text = "\n".join(
            [f"[{r.role}] {r.summary} (score={r.score})" for r in reports]
        )
        history = []
        bull = ""
        bear = ""

        for i in range(self.n_rounds):
            bull_prompt = f"基於以下分析報告，為 {symbol} 提出最強多頭論點。第 {i + 1} 輪。\n報告：\n{report_text}\n\n歷史辯論：\n{history}"
            bear_prompt = f"基於以下分析報告，為 {symbol} 提出最強空頭論點。第 {i + 1} 輪。\n報告：\n{report_text}\n\n歷史辯論：\n{history}"

            try:
                bull = await self.llm.chat([{"role": "user", "content": bull_prompt}])
            except Exception as e:
                bull = f"[多頭辯論失敗: {e}]"
            try:
                bear = await self.llm.chat([{"role": "user", "content": bear_prompt}])
            except Exception as e:
                bear = f"[空頭辯論失敗: {e}]"

            history.append({"round": i + 1, "bull": bull, "bear": bear})

        return DebateResult(bull_case=bull, bear_case=bear, rounds=history)
