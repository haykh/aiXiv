import httpx

from aiXiv.defaults import Defaults
from aiXiv.llm.base import LLMClient


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        schema=None,
        temperature: float = Defaults.LLM_TEMPERATURE,
    ) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": temperature},
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
            except httpx.HTTPError:
                return []
