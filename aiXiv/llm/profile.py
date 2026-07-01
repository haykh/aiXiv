from pydantic import BaseModel

from aiXiv.defaults import Defaults
from aiXiv.database.db import get_settings, Session
from aiXiv.database.tables import Profile, Paper
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


async def refine_profile(
    profile: Profile,
    feedback: list[tuple[Paper, float | None, int]],
    session: Session,
) -> ProfileExtraction:
    """Rewrite a profile's summary + keywords from the user's 0-10 ratings.
    feedback items are (paper, ai_score, user_score)."""
    settings = get_settings(session)
    client = get_llm_client(settings)

    rated = "\n".join(
        f"- user rated {user}/10 (AI said {'%.0f' % ai if ai is not None else 'n/a'}): {paper.title}\n"
        f"  {paper.abstract[:300]}"
        for paper, ai, user in feedback
    )

    response = await client.generate(
        messages=[
            {
                "role": "system",
                "content": "You refine an existing researcher interest profile using their feedback. "
                "They rated papers 0-10 for how relevant each ACTUALLY is to them.\n"
                "- Emphasize topics/methods from highly-rated papers.\n"
                "- De-emphasize topics that appear only in low-rated papers.\n"
                "- Stay grounded in the original profile and the rated papers; do not invent new interests.\n"
                "Produce an updated summary (a dense paragraph, comparable against abstracts) "
                "and keyword list. Respond as JSON.",
            },
            {
                "role": "user",
                "content": f"Current profile:\nsummary: {profile.summary}\n"
                f"keywords: {', '.join(profile.keywords)}\n\n"
                f"Rated papers:\n{rated}",
            },
        ],
        schema=ProfileExtraction.model_json_schema(),
        temperature=Defaults.LLM_TEMPERATURE,
    )
    return ProfileExtraction.model_validate_json(response)
