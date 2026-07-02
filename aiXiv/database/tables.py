from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Column, JSON, UniqueConstraint

from aiXiv.settings import Defaults


class Profile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="")
    raw_text: str = Field(default="")  # the researcher's pasted text
    summary: str = Field(default="")  # LLM-written interest summary
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class Library(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("profile_id", "paper_id"),)
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Paper(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("arxiv_id"),)
    id: int | None = Field(default=None, primary_key=True)
    arxiv_id: str = Field(default="")
    title: str = Field(default="")
    abstract: str = Field(default="")
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    published_at: datetime = Field()
    url: str = Field(default="")


class Score(SQLModel, table=True):
    """The AI's relevance ranking of a paper for a profile (0-10)."""

    __table_args__ = (UniqueConstraint("profile_id", "paper_id"),)
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    paper_id: int = Field(foreign_key="paper.id")
    score: float = Field()
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class Vote(SQLModel, table=True):
    """The user's own relevance rating of a paper for a profile (0-10)."""

    __table_args__ = (UniqueConstraint("profile_id", "paper_id"),)
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    paper_id: int = Field(foreign_key="paper.id")
    score: int = Field(ge=0, le=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class Bookmark(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("profile_id", "paper_id"),)
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id")
    paper_id: int = Field(foreign_key="paper.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class Seen(SQLModel, table=True):
    """Papers a profile has marked as seen; kept even after library removal
    so browse doesn't re-select them for import."""

    __table_args__ = (UniqueConstraint("profile_id", "paper_id"),)
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Setting(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    llm_provider: str = Field(default=Defaults.LLM_PROVIDER)
    llm_model: str = Field(default=Defaults.LLM_MODEL)
    ollama_api_url: str = Field(default=Defaults.OLLAMA_API_URL)
    claude_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
