import asyncio

from aiXiv.database.tables import Setting
from aiXiv.llm import get_llm_client

settings = Setting(
    llm_provider="ollama",
    llm_model="deepseek-r1:latest",
    ollama_api_url="http://172.29.96.1:11434",
)

client = get_llm_client(settings)

print(
    asyncio.run(
        client.generate(
            messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        )
    )
)
