from pydantic import BaseModel, Field
from sqlmodel import select

from aiXiv.defaults import Defaults
from aiXiv.database.db import get_settings, Session
from aiXiv.database.tables import Profile, Score, Paper
from aiXiv.llm import get_llm_client


class PaperScore(BaseModel):
    arxiv_id: str
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
                "content": "Score how relevant the paper is to the researcher's profile, 0-10, using their summary and keywords.\n"
                + "Give a score and a one-line reason. Score on topical match, not general quality. Respond as JSON.",
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
    # commit per paper so ranked papers land in the DB one at a time, not all at the end
    session.commit()
    return score


async def rank_papers(
    profile: Profile,
    papers: list[Paper],
    session: Session,
) -> list[Score]:
    client = get_llm_client(get_settings(session))
    return [await rank_one_paper(profile, paper, client, session) for paper in papers]
