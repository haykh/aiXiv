import os
import sqlite3
from typing import Annotated
from pathlib import Path

from fastapi import Depends
from sqlmodel import (
    SQLModel,
    Session,
    select,
    create_engine,
)

from aiXiv.defaults import Defaults
from aiXiv.database.tables import Setting


DB_PATH = Path(os.environ.get("AIXIV_DB_PATH", Defaults.DB_PATH))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db_filename = str(DB_PATH)
db_url = f"sqlite:///{db_filename}"

connect_args = {"check_same_thread": False}
engine = create_engine(db_url, connect_args=connect_args)


def initialize_db():
    SQLModel.metadata.create_all(engine)
    _ensure_setting_columns()
    _rename_profile_columns()


def _ensure_setting_columns():
    con = sqlite3.connect(db_filename)
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(setting)")}
        for col in ("claude_api_key", "openai_api_key"):
            if col not in existing:
                con.execute(f"ALTER TABLE setting ADD COLUMN {col} VARCHAR DEFAULT ''")
        con.commit()
    finally:
        con.close()


def _rename_profile_columns():
    """Migrate the old raw_profile/summary_profile columns to their new names."""
    renames = {"raw_profile": "raw_text", "summary_profile": "summary"}
    con = sqlite3.connect(db_filename)
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(profile)")}
        for old, new in renames.items():
            if old in existing and new not in existing:
                con.execute(f"ALTER TABLE profile RENAME COLUMN {old} TO {new}")
        con.commit()
    finally:
        con.close()


def get_session():
    with Session(engine) as session:
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
