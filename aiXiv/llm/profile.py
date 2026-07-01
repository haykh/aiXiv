from pydantic import BaseModel

from aiXiv.defaults import Defaults
from aiXiv.database.db import get_settings, Session
from aiXiv.database.tables import Profile
from aiXiv.llm import get_llm_client


class ProfileExtraction(BaseModel):
    summary: str
    keywords: list[str]


async def analyze_text(text: str, session: Session) -> ProfileExtraction:
    """Run the LLM extraction only — no DB write. Used by the preview step."""
    settings = get_settings(session)
    client = get_llm_client(settings)
    response = await client.generate(
        messages=[
            {
                "role": "system",
                "content": "You build an academic interest profile from a researcher's own words (bio, abstracts, descriptions of past work).\n\n"
                + "Extract:\n"
                + "- summary: a dense paragraph describing their research topics, methods, and the kinds of problems they care about — written so it can be compared against paper abstracts to judge relevance.\n"
                + '- keywords: specific topical phrases (subfields, methods, objects of study), not generic terms. Prefer "tidal disruption events" over "astrophysics"\n\n'
                + "Base everything ONLY on the provided text; do not invent interests. Respond as JSON.",
            },
            {
                "role": "user",
                "content": f"Researcher's text:\n<<<\n{text}\n>>>",
            },
        ],
        schema=ProfileExtraction.model_json_schema(),
        temperature=Defaults.LLM_TEMPERATURE,
    )
    return ProfileExtraction.model_validate_json(response)


def save_profile(
    name: str,
    raw_text: str,
    summary: str,
    keywords: list[str],
    session: Session,
) -> Profile:
    """Persist a profile from (possibly user-edited) fields — no LLM call."""
    profile = Profile(
        name=name,
        raw_text=raw_text,
        summary=summary,
        keywords=keywords,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
