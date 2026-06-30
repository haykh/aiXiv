from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str: ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return the model names available from this provider."""
        ...
