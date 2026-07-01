from pydantic import BaseModel, Field
from sqlmodel import select

from aiXiv.settings import Defaults, Prompts
from aiXiv.database.db import get_settings, Session
from aiXiv.database.tables import Profile, Score, Paper
from aiXiv.llm import get_llm_client


class PaperScore(BaseModel):
    score: float = Field(ge=0, le=10)
    reason: str


async def rank_one_paper(
    profile: Profile,
    paper: Paper,
    client,
    session: Session,
) -> Score:
    """Rank a single paper against the profile, upsert its Score, and commit it."""
    response = await client.generate(
        messages=[
            {
                "role": "system",
                "content": Prompts.PAPER_SCORE,
            },
            {
                "role": "user",
                "content": "Researcher's profile:\n"
                + f"summary: {profile.summary}\n"
                + f"keywords: {', '.join(profile.keywords)}\n\n"
                + "Paper:\n"
                + f"title: {paper.title}\n"
                + f"abstract: {paper.abstract}\n",
            },
        ],
        schema=PaperScore.model_json_schema(),
        temperature=Defaults.LLM_TEMPERATURE,
    )
    ranking_data = PaperScore.model_validate_json(response)
    existing = session.exec(
        select(Score).where(
            Score.profile_id == profile.id,
            Score.paper_id == paper.id,
        )
    ).first()
    if existing is not None:
        existing.score = ranking_data.score
        existing.reason = ranking_data.reason
        score = existing
    else:
        score = Score(
            profile_id=profile.id,
            paper_id=paper.id,
            score=ranking_data.score,
            reason=ranking_data.reason,
        )
        session.add(score)
    session.commit()
    return score


async def rank_papers(
    profile: Profile,
    papers: list[Paper],
    session: Session,
) -> list[Score]:
    client = get_llm_client(get_settings(session))
    return [await rank_one_paper(profile, paper, client, session) for paper in papers]
