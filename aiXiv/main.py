import json
import math
import logging
from datetime import datetime
import os
from pathlib import Path
from functools import lru_cache
from contextlib import asynccontextmanager
from typing import Annotated

import typer
import uvicorn
from markupsafe import Markup
from fastapi import FastAPI, Request, Form, Response, Query
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import nullslast
from sqlmodel import select, Session

from aiXiv import __version__
from aiXiv.settings import Defaults
from aiXiv.database.db import initialize_db, SessionDep, get_settings, get_engine
from aiXiv.database.tables import Profile, Score, Paper, Library, Vote, Bookmark, Seen
from aiXiv.utils.latex2html import latex_to_html
from aiXiv.utils.timeago import timeago
from aiXiv.llm import get_llm_client
from aiXiv.llm.profile import analyze_text, save_profile, refine_profile
from aiXiv.llm.papers import rank_one_paper
from aiXiv.llm.ollama import OllamaClient
from aiXiv.llm.cli import CodexCLIClient
from aiXiv.arxiv.arxiv import fetch_from_arxiv, fetch_from_arxiv_by_ids, store_papers
from aiXiv.arxiv.categories import ArxivCategory


logging.basicConfig(
    level=logging.INFO, format="%(levelname)s:     [%(name)s] %(message)s"
)

# ───────────────────────── FastAPI app ─────────────────────────


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_db()
    yield


app = FastAPI(
    title="aiXiv",
    version=__version__,
    description="A personalized digest from the arXiv.",
    lifespan=lifespan,
)

root_path = Path(__file__).parent

app.mount("/static", StaticFiles(directory=str(root_path / "static")), name="static")
app.mount(
    "/katex",
    StaticFiles(directory=str(root_path / "static" / "vendor" / "katex")),
    name="katex",
)
app.mount(
    "/htmx",
    StaticFiles(directory=str(root_path / "static" / "vendor")),
    name="htmx",
)
templates = Jinja2Templates(directory=str(root_path / "templates"))
templates.env.filters["latex"] = latex_to_html
templates.env.filters["timeago"] = timeago

_icons_dir = root_path / "static" / "vendor" / "icons"


@lru_cache
def icon(name: str) -> Markup:
    """Inline a lucide SVG so it inherits text color (stroke="currentColor")."""
    return Markup((_icons_dir / f"{name}.svg").read_text())


templates.env.globals["icon"] = icon


# sortable columns per library tab; the first entry is that tab's default
LIBRARY_SORTS = {
    "new": {"published": Paper.published_at, "imported": Library.created_at},
    "ranked": {
        "score": Score.score,
        "date": Score.updated_at,
        "published": Paper.published_at,
    },
    "bookmarked": {
        "added": Bookmark.created_at,
        "published": Paper.published_at,
        "score": Score.score,
    },
    "seen": {
        "seen": Seen.created_at,
        "published": Paper.published_at,
        "score": Score.score,
    },
}


def library_context(
    session: SessionDep,
    profile: Profile,
    active_tab: str = "new",
    sort: str = "",
    order: str = "",
    page: int = 1,
):
    per_page = Defaults.LIBRARY_PAGE_SIZE
    pid = profile.id
    votes = {
        v.paper_id: v.score
        for v in session.exec(select(Vote).where(Vote.profile_id == pid)).all()
    }
    # AI score per paper, for cross-tab display (bookmarked/seen show it too)
    scores = {
        s.paper_id: s
        for s in session.exec(select(Score).where(Score.profile_id == pid)).all()
    }
    bookmark_ids = set(
        session.exec(select(Bookmark.paper_id).where(Bookmark.profile_id == pid)).all()
    )
    seen_ids = set(
        session.exec(select(Seen.paper_id).where(Seen.profile_id == pid)).all()
    )

    def tab_order(tab: str) -> tuple[str, str, int]:
        """Resolve (sort, order, page) — request values for the active tab, defaults otherwise."""
        if tab == active_tab:
            return (
                sort if sort in LIBRARY_SORTS[tab] else next(iter(LIBRARY_SORTS[tab])),
                order if order in ("asc", "desc") else "desc",
                max(1, page),
            )
        return next(iter(LIBRARY_SORTS[tab])), "desc", 1

    def tab_state(tab: str, rows: list) -> dict:
        """Slice one tab's full row list down to its current page."""
        tab_sort, tab_dir, tab_page = tab_order(tab)
        pages = max(1, math.ceil(len(rows) / per_page))
        tab_page = min(tab_page, pages)
        return {
            "rows": rows[(tab_page - 1) * per_page : tab_page * per_page],
            "total": len(rows),
            "page": tab_page,
            "pages": pages,
            "sort": tab_sort,
            "order": tab_dir,
        }

    def order_clause(tab: str):
        tab_sort, tab_dir, _ = tab_order(tab)
        col = LIBRARY_SORTS[tab][tab_sort]
        return nullslast(col.asc() if tab_dir == "asc" else col.desc())

    not_scored = Score.id == None  # noqa: E711
    not_seen = Seen.id == None  # noqa: E711
    new = session.exec(
        select(Paper)
        .join(Library, Library.paper_id == Paper.id)
        .outerjoin(Score, (Score.paper_id == Paper.id) & (Score.profile_id == pid))
        .outerjoin(Seen, (Seen.paper_id == Paper.id) & (Seen.profile_id == pid))
        .where(Library.profile_id == pid, not_scored, not_seen)
        .order_by(order_clause("new"))
    ).all()
    ranked = session.exec(
        select(Score, Paper)
        .join(Paper)
        .outerjoin(Seen, (Seen.paper_id == Paper.id) & (Seen.profile_id == pid))
        .where(Score.profile_id == pid, not_seen)
        .order_by(order_clause("ranked"))
    ).all()
    bookmarked = session.exec(
        select(Paper)
        .join(Bookmark, Bookmark.paper_id == Paper.id)
        .outerjoin(Score, (Score.paper_id == Paper.id) & (Score.profile_id == pid))
        .where(Bookmark.profile_id == pid)
        .order_by(order_clause("bookmarked"))
    ).all()
    seen = session.exec(
        select(Paper)
        .join(Seen, Seen.paper_id == Paper.id)
        .join(Library, (Library.paper_id == Paper.id) & (Library.profile_id == pid))
        .outerjoin(Score, (Score.paper_id == Paper.id) & (Score.profile_id == pid))
        .where(Seen.profile_id == pid)
        .order_by(order_clause("seen"))
    ).all()

    return {
        "profile": profile,
        "votes": votes,
        "vote_count": len(votes),
        "scores": scores,
        "active_tab": active_tab,
        "bookmark_ids": bookmark_ids,
        "seen_ids": seen_ids,
        "tabs": {
            "new": tab_state("new", new),
            "ranked": tab_state("ranked", ranked),
            "bookmarked": tab_state("bookmarked", bookmarked),
            "seen": tab_state("seen", seen),
        },
    }


def library_response(
    request: Request,
    session: SessionDep,
    profile_id: int,
    active_tab: str = "new",
    sort: str = "",
    order: str = "",
    page: int = 1,
):
    """Re-render the library partial — the response shape most routes share."""
    profile = session.get(Profile, profile_id)
    return templates.TemplateResponse(
        request,
        "_library_oob.html",
        library_context(session, profile, active_tab, sort, order, page),
    )


def purge_papers(session: SessionDep, profile_id: int, paper_ids: list[int]):
    """Remove a profile's rows (library link, score, vote, bookmark) for given papers.

    Seen rows are kept on purpose: they stop browse from re-selecting the paper
    for import even after it leaves the library.
    """
    if not paper_ids:
        return
    for model in (Library, Score, Vote, Bookmark):
        for row in session.exec(
            select(model).where(
                model.profile_id == profile_id, model.paper_id.in_(paper_ids)
            )
        ).all():
            session.delete(row)
    session.commit()


def purge_profile(session: SessionDep, profile_id: int):
    """Delete all of a profile's dependent rows, then the profile itself."""
    for model in (Score, Vote, Bookmark, Seen, Library):
        for row in session.exec(
            select(model).where(model.profile_id == profile_id)
        ).all():
            session.delete(row)
    profile = session.get(Profile, profile_id)
    if profile:
        session.delete(profile)
    session.commit()


async def browse_context(
    session: SessionDep,
    profile: Profile,
    category: str,
    start: str,
    end: str,
    page: int,
    per_page: int,
):
    papers, total = await fetch_from_arxiv(
        ArxivCategory(category),
        page,
        datetime.strptime(start, "%Y-%m-%d"),
        datetime.strptime(end, "%Y-%m-%d"),
        per_page,
    )
    ids = [p.arxiv_id for p in papers]
    imported = set(
        session.exec(
            select(Paper.arxiv_id)
            .join(Library, Library.paper_id == Paper.id)
            .where(
                Library.profile_id == profile.id,
                Paper.arxiv_id.in_(ids),
            )
        ).all()
    )
    # seen papers stay selectable but are skipped by "select all"
    seen = set(
        session.exec(
            select(Paper.arxiv_id)
            .join(Seen, Seen.paper_id == Paper.id)
            .where(
                Seen.profile_id == profile.id,
                Paper.arxiv_id.in_(ids),
            )
        ).all()
    )
    total_pages = max(1, math.ceil(total / per_page))
    return {
        "papers": papers,
        "imported": imported,
        "seen": seen,
        "profile": profile,
        "category": category,
        "start": start,
        "end": end,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }


@app.get("/")
async def index(request: Request, session: SessionDep, profile_id: int | None = None):
    profiles = session.exec(select(Profile).order_by(Profile.name)).all()
    profile = (
        session.get(Profile, profile_id)
        if profile_id
        else (profiles[0] if profiles else None)
    )
    ctx = {
        "profiles": profiles,
        "profile": profile,
        "categories": [c.value for c in ArxivCategory],
        "settings": get_settings(session),
        "browse_page_size": Defaults.BROWSE_PAGE_SIZE,
    }
    if profile is not None:
        ctx |= library_context(session, profile)
    return templates.TemplateResponse(request, "main.html", ctx)


@app.post("/profiles/preview")
async def preview_profile(
    request: Request,
    session: SessionDep,
    name: str = Form(...),
    raw_text: str = Form(...),
    profile_id: int | None = Form(None),
):
    extraction = await analyze_text(raw_text, session)
    return templates.TemplateResponse(
        request,
        "_profile_preview.html",
        {
            "name": name,
            "raw_text": raw_text,
            "summary": extraction.summary,
            "keywords": extraction.keywords,
            "profile_id": profile_id,
        },
    )


@app.get("/profiles/edit")
async def edit_profile(request: Request, session: SessionDep, profile_id: int):
    profile = session.get(Profile, profile_id)
    return templates.TemplateResponse(
        request,
        "_profile_preview.html",
        {
            "name": profile.name,
            "raw_text": profile.raw_text,
            "summary": profile.summary,
            "keywords": profile.keywords,
            "profile_id": profile.id,
        },
    )


@app.post("/profiles/create")
async def create_profile(
    session: SessionDep,
    name: str = Form(...),
    raw_text: str = Form(...),
    summary: str = Form(...),
    keywords: str = Form(""),
):
    kw = [k.strip() for k in keywords.split(",") if k.strip()]
    profile = save_profile(name, raw_text, summary, kw, session)
    return Response(headers={"HX-Redirect": f"/?profile_id={profile.id}"})


@app.post("/profiles/update")
async def update_profile_route(
    session: SessionDep,
    profile_id: int = Form(...),
    name: str = Form(...),
    raw_text: str = Form(...),
    summary: str = Form(...),
    keywords: str = Form(""),
):
    kw = [k.strip() for k in keywords.split(",") if k.strip()]
    profile = session.get(Profile, profile_id)
    profile.name, profile.raw_text, profile.summary, profile.keywords = (
        name,
        raw_text,
        summary,
        kw,
    )
    session.add(profile)
    session.commit()
    return Response(headers={"HX-Redirect": f"/?profile_id={profile.id}"})


@app.get("/papers/browse")
async def browse(
    request: Request,
    session: SessionDep,
    profile_id: int,
    category: str,
    start: str,
    end: str,
    page: int = 1,
    per_page: int = Defaults.BROWSE_PAGE_SIZE,
):
    if category not in {c.value for c in ArxivCategory}:
        return HTMLResponse(
            '<p class="empty">Unknown arXiv category — pick one from the suggestions.</p>'
        )
    profile = session.get(Profile, profile_id)
    ctx = await browse_context(session, profile, category, start, end, page, per_page)
    return templates.TemplateResponse(request, "_browse.html", ctx)


@app.post("/papers/import")
async def import_papers(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    category: str = Form(...),
    start: str = Form(...),
    end: str = Form(...),
    page: int = Form(1),
    per_page: int = Form(Defaults.BROWSE_PAGE_SIZE),
    arxiv_ids: list[str] = Form([]),
):
    profile = session.get(Profile, profile_id)
    if arxiv_ids:
        store_papers(await fetch_from_arxiv_by_ids(arxiv_ids), session)
    papers = session.exec(select(Paper).where(Paper.arxiv_id.in_(arxiv_ids))).all()
    for p in papers:
        exists = session.exec(
            select(Library).where(
                Library.profile_id == profile_id,
                Library.paper_id == p.id,
            )
        ).first()
        if not exists:
            session.add(
                Library(
                    profile_id=profile_id,
                    paper_id=p.id,
                )
            )
    session.commit()

    ctx = await browse_context(session, profile, category, start, end, page, per_page)
    ctx |= library_context(session, profile)
    return templates.TemplateResponse(request, "_import_response.html", ctx)


@app.get("/library")
async def library(
    request: Request,
    session: SessionDep,
    profile_id: int,
    active_tab: str = "new",
    sort: str = "",
    order: str = "",
    page: int = 1,
):
    profile = session.get(Profile, profile_id)
    return templates.TemplateResponse(
        request,
        "_library.html",
        library_context(session, profile, active_tab, sort, order, page),
    )


def _sse(payload: dict) -> str:
    """Format one Server-Sent Event line."""
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/digest/rank/stream")
async def rank_stream(profile_id: int, paper_ids: list[int] = Query(default=[])):
    """Rank the selected papers one at a time, streaming progress as SSE events.

    Each paper is committed as it's scored (see rank_one_paper), so ranked papers
    appear in the DB incrementally rather than all at once.
    """

    async def event_gen():
        # a dedicated session: the stream outlives the normal request/response cycle
        with Session(get_engine()) as session:
            try:
                profile = session.get(Profile, profile_id)
                papers = (
                    session.exec(select(Paper).where(Paper.id.in_(paper_ids))).all()
                    if paper_ids
                    else []
                )
                client = get_llm_client(get_settings(session))
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done", "total": 0})
                return

            total = len(papers)
            for i, paper in enumerate(papers):
                # announce the paper about to be ranked (done = number finished so far)
                yield _sse(
                    {
                        "type": "progress",
                        "done": i,
                        "total": total,
                        "title": paper.title,
                    }
                )
                try:
                    await rank_one_paper(profile, paper, client, session)
                except Exception as exc:
                    yield _sse(
                        {"type": "error", "title": paper.title, "message": str(exc)}
                    )
            yield _sse({"type": "done", "total": total})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/scores/delete")
async def delete_score(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    score = session.exec(
        select(Score).where(Score.profile_id == profile_id, Score.paper_id == paper_id)
    ).first()
    if score:
        session.delete(score)
        session.commit()
    return library_response(request, session, profile_id, "ranked", sort, order, page)


@app.post("/scores/delete-selected")
async def delete_selected_scores(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_ids: list[int] = Form([]),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    """Unrank selected papers (drop their Score rows; the papers stay in the library)."""
    if paper_ids:
        scores = session.exec(
            select(Score).where(
                Score.profile_id == profile_id,
                Score.paper_id.in_(paper_ids),
            )
        ).all()
        for score in scores:
            session.delete(score)
        session.commit()
    return library_response(request, session, profile_id, "ranked", sort, order, page)


@app.post("/library/remove-selected")
async def remove_selected_from_library(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_ids: list[int] = Form([]),
    active_tab: str = Form("new"),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    """Remove one or many papers from the library (a single card sends one id)."""
    purge_papers(session, profile_id, paper_ids)
    return library_response(request, session, profile_id, active_tab, sort, order, page)


@app.post("/profiles/delete")
async def delete_profile(
    session: SessionDep,
    profile_id: int = Form(...),
):
    purge_profile(session, profile_id)
    return RedirectResponse("/", status_code=303)


@app.get("/settings/models")
async def settings_models(request: Request, session: SessionDep, ollama_api_url: str):
    models = await OllamaClient(ollama_api_url, "").list_models()
    settings = get_settings(session)
    return templates.TemplateResponse(
        request,
        "_settings_models.html",
        {"models": models, "llm_model": settings.llm_model},
    )


@app.get("/settings/fields")
async def settings_fields(request: Request, session: SessionDep, llm_provider: str):
    settings = get_settings(session)
    models = []
    if llm_provider == "ollama":
        models = await OllamaClient(settings.ollama_api_url, "").list_models()
    elif llm_provider == "codex-cli":
        models = await CodexCLIClient("").list_models()
    return templates.TemplateResponse(
        request,
        "_settings_fields.html",
        {
            "provider": llm_provider,
            "settings": settings,
            "models": models,
            "llm_model": settings.llm_model,
        },
    )


@app.post("/settings")
async def save_settings(
    session: SessionDep,
    llm_provider: str = Form(...),
    llm_model: str = Form(""),
    ollama_api_url: str = Form(""),
    claude_api_key: str = Form(""),
    openai_api_key: str = Form(""),
):
    settings = get_settings(session)
    settings.llm_provider = llm_provider
    settings.llm_model = llm_model
    if llm_provider == "ollama":
        settings.ollama_api_url = ollama_api_url or settings.ollama_api_url
    elif llm_provider == "claude":
        settings.claude_api_key = claude_api_key
    elif llm_provider == "openai":
        settings.openai_api_key = openai_api_key
    session.add(settings)
    session.commit()
    return Response(status_code=204)


@app.post("/votes")
async def vote(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    score: int = Form(...),
):
    existing = session.exec(
        select(Vote).where(Vote.profile_id == profile_id, Vote.paper_id == paper_id)
    ).first()
    if existing:
        existing.score = score
    else:
        session.add(Vote(profile_id=profile_id, paper_id=paper_id, score=score))
    session.commit()
    profile = session.get(Profile, profile_id)
    count = len(session.exec(select(Vote).where(Vote.profile_id == profile_id)).all())
    return templates.TemplateResponse(
        request,
        "_refine_slot.html",
        {"profile": profile, "vote_count": count, "oob": True},
    )


@app.post("/votes/delete")
async def delete_vote(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    active_tab: str = Form("ranked"),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    existing = session.exec(
        select(Vote).where(Vote.profile_id == profile_id, Vote.paper_id == paper_id)
    ).first()
    if existing:
        session.delete(existing)
        session.commit()
    return library_response(request, session, profile_id, active_tab, sort, order, page)


@app.post("/profiles/refine")
async def refine_route(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
):
    profile = session.get(Profile, profile_id)
    votes = session.exec(
        select(Vote, Paper)
        .join(Paper, Vote.paper_id == Paper.id)
        .where(Vote.profile_id == profile_id)
    ).all()
    if votes:
        ai = {
            s.paper_id: s.score
            for s in session.exec(
                select(Score).where(Score.profile_id == profile_id)
            ).all()
        }
        feedback = [(paper, ai.get(paper.id), vote.score) for vote, paper in votes]
        extraction = await refine_profile(profile, feedback, session)
        profile.summary = extraction.summary
        profile.keywords = extraction.keywords
        session.add(profile)
        session.commit()
    return templates.TemplateResponse(
        request,
        "_profile_summary.html",
        {"profile": profile, "vote_count": len(votes), "open": True},
    )


@app.post("/bookmarks/toggle")
async def toggle_bookmark(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    active_tab: str = Form("new"),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    existing = session.exec(
        select(Bookmark).where(
            Bookmark.profile_id == profile_id, Bookmark.paper_id == paper_id
        )
    ).first()
    if existing:
        session.delete(existing)
    else:
        session.add(Bookmark(profile_id=profile_id, paper_id=paper_id))
    session.commit()
    return library_response(request, session, profile_id, active_tab, sort, order, page)


@app.post("/seen/toggle")
async def toggle_seen(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    active_tab: str = Form("new"),
    sort: str = Form(""),
    order: str = Form(""),
    page: int = Form(1),
):
    existing = session.exec(
        select(Seen).where(Seen.profile_id == profile_id, Seen.paper_id == paper_id)
    ).first()
    if existing:
        session.delete(existing)
    else:
        session.add(Seen(profile_id=profile_id, paper_id=paper_id))
    session.commit()
    return library_response(request, session, profile_id, active_tab, sort, order, page)


# ───────────────────────── Typer CLI app ─────────────────────────

cliapp = typer.Typer(add_completion=False)


def version_callback(value: bool):
    if value:
        print(f"aiXiv: {__version__}")
        raise typer.Exit()


@cliapp.command()
def main(
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Host to bind the server to",
        ),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to bind the server to",
        ),
    ] = 8000,
    db: Annotated[
        Path | None,
        typer.Option(
            "--db",
            "-d",
            help="Path to the SQLite database file",
            dir_okay=False,
        ),
    ] = None,
    _: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show the version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
):

    if db is not None:
        os.environ["AIXIV_DB_PATH"] = str(db.expanduser().resolve())

    uvicorn.run(app, host=host, port=port)


def run():
    cliapp()
