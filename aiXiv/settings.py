from pathlib import Path


class Defaults:
    DB_PATH: str = str(Path.home() / ".aiXiv" / "app.db")
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "gpt-oss:20b"
    OLLAMA_API_URL: str = "http://localhost:11434"
    BROWSE_PAGE_SIZE: int = 20
    LLM_TEMPERATURE: float = 0.2


class Prompts:
    PAPER_SCORE: str = (
        "Score 0-10 how relevant the paper is to the researcher, using their profile summary and keywords.\n"
        "Judge relevance by SUBJECT MATTER — the phenomena, objects/systems, and scientific questions "
        "the paper is about — NOT by shared methods, tools, software, codes, or numerical techniques.\n"
        "A paper on the same subject with a different method IS relevant (score high).\n"
        "Rate topical match and potential interest, not general quality or novelty.\n"
        "Give the score and a one-line reason that names the shared or missing topic. Respond as JSON."
    )
    PROFILE_EXTRACTION: str = (
        "You build an academic interest profile from a researcher's own words "
        "(bio, published abstracts, descriptions of past work).\n\n"
        "Extract:\n"
        "- summary: a dense paragraph describing their research topics, and the kinds of problems they care about, "
        "written so it can be compared against paper abstracts to judge relevance.\n"
        "- keywords: specific topical phrases (subfields, objects of study), not generic terms. "
        'For example, prefer "tidal disruption events" over "astrophysics", '
        "and never list specific software as keywords.\n\n"
        "Base everything ONLY on the provided text; do not invent interests. "
        "Do NOT focus on specific methodologies, numerical tools etc; "
        "instead emphasize scientific concepts and topics.\n"
        "Respond as JSON."
    )
    PROFILE_REFINEMENT: str = (
        "You refine an existing researcher interest profile using their feedback. "
        "They rated papers 0-10 for how relevant each ACTUALLY is to them.\n"
        "- Emphasize the subjects/phenomena/topics from highly-rated papers; "
        "de-emphasize those only in low-rated papers.\n"
        "- Judge by subject matter, not shared methods or tools.\n"
        "- Stay grounded in the original profile and the rated papers; do not invent new interests.\n"
        "Produce an updated summary (a dense paragraph, comparable against abstracts) and a keyword list. "
        "Respond as JSON."
    )
