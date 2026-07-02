import os
import sqlite3
from typing import Annotated
from pathlib import Path
from functools import lru_cache

from fastapi import Depends
from sqlmodel import (
    SQLModel,
    Session,
    select,
    create_engine,
)

from aiXiv.settings import Defaults
from aiXiv.database.tables import Setting


def db_path() -> Path:
    return Path(os.environ.get("AIXIV_DB_PATH", Defaults.DB_PATH)).expanduser()


@lru_cache
def get_engine():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def initialize_db():
    SQLModel.metadata.create_all(get_engine())
    _ensure_setting_columns()
    _rename_profile_columns()


def _ensure_setting_columns():
    con = sqlite3.connect(db_path())
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(setting)")}
        for col in ("claude_api_key", "openai_api_key"):
            if col not in existing:
                con.execute(f"ALTER TABLE setting ADD COLUMN {col} VARCHAR DEFAULT ''")
        con.commit()
    finally:
        con.close()


def _rename_profile_columns():
    renames = {"raw_profile": "raw_text", "summary_profile": "summary"}
    con = sqlite3.connect(db_path())
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(profile)")}
        for old, new in renames.items():
            if old in existing and new not in existing:
                con.execute(f"ALTER TABLE profile RENAME COLUMN {old} TO {new}")
        con.commit()
    finally:
        con.close()


def get_session():
    with Session(get_engine()) as session:
        yield session


def get_settings(session: Session) -> Setting:
    settings = session.exec(select(Setting)).first()
    if settings is None:
        settings = Setting()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


SessionDep = Annotated[Session, Depends(get_session)]
