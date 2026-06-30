from aiXiv.database.tables import Setting
from aiXiv.llm.base import LLMClient
from aiXiv.llm.ollama import OllamaClient


def get_llm_client(settings: Setting) -> LLMClient:
    if settings.llm_provider == "ollama":
        return OllamaClient(settings.ollama_api_url, settings.llm_model)
    raise ValueError(f"unknown provider: {settings.llm_provider}")
