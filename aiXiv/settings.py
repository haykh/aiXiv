class Defaults:
    DB_PATH: str = "./data/app.db"
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "gpt-oss:20b"
    OLLAMA_API_URL: str = "http://localhost:11434"
    BROWSE_PAGE_SIZE: int = 20
    LLM_TEMPERATURE: float = 0.2


class Prompts:
    PAPER_SCORE: str = (
        "Score how relevant the paper is to the researcher's profile, 0-10, using their summary and keywords.\n"
        + "Give a score and a one-line reason. Score on topical match, not general quality. Respond as JSON."
    )
    PROFILE_EXTRACTION: str = (
        "You build an academic interest profile from a researcher's own words (bio, abstracts, descriptions of past work).\n\n"
        + "Extract:\n"
        + "- summary: a dense paragraph describing their research topics, methods, and the kinds of problems they care about — written so it can be compared against paper abstracts to judge relevance.\n"
        + '- keywords: specific topical phrases (subfields, methods, objects of study), not generic terms. Prefer "tidal disruption events" over "astrophysics"\n\n'
        + "Base everything ONLY on the provided text; do not invent interests. Respond as JSON.",
    )
    PROFILE_REFINEMENT: str = (
        "You refine an existing researcher interest profile using their feedback. "
        "They rated papers 0-10 for how relevant each ACTUALLY is to them.\n"
        "- Emphasize topics/methods from highly-rated papers.\n"
        "- De-emphasize topics that appear only in low-rated papers.\n"
        "- Stay grounded in the original profile and the rated papers; do not invent new interests.\n"
        "Produce an updated summary (a dense paragraph, comparable against abstracts) "
        "and keyword list. Respond as JSON.",
    )
