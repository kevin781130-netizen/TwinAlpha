import httpx

from app.config import settings


class LLMClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout: float = 60.0):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout

    async def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        if not self.api_key:
            last = messages[-1]["content"] if messages else ""
            return f"[MOCK LLM] {last[:800]}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"[LLM HTTP Error {e.response.status_code}] {e.response.text[:500]}"
        except httpx.TimeoutException:
            return f"[LLM Timeout after {self.timeout}s]"
        except Exception as e:
            return f"[LLM Error] {type(e).__name__}: {e}"
