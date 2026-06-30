class classproperty(property):
    def __get__(self, _, owner_cls):
        return self.fget(owner_cls)


class Defaults:
    @classproperty
    def DB_PATH(cls) -> str:
        return "./data/app.db"

    @classproperty
    def LLM_PROVIDER(cls) -> str:
        return "ollama"

    @classproperty
    def LLM_MODEL(cls) -> str:
        return "deepseek-r1:latest"

    @classproperty
    def OLLAMA_API_URL(cls) -> str:
        return "http://172.29.96.1:11434"

    @classproperty
    def BROWSE_PAGE_SIZE(cls) -> int:
        return 20

    @classproperty
    def LLM_TEMPERATURE(cls) -> float:
        return 0.2
