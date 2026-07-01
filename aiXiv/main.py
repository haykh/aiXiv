import math
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from contextlib import asynccontextmanager

from markupsafe import Markup
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from aiXiv import __version__
from aiXiv.defaults import Defaults
from aiXiv.database.db import initialize_db, SessionDep, get_settings
from aiXiv.database.tables import Profile, Score, Paper, Library, Vote, Bookmark
from aiXiv.utils.latex2html import latex_to_html
from aiXiv.utils.timeago import timeago
from aiXiv.llm.profile import analyze_text, save_profile
from aiXiv.llm.papers import rank_papers
from aiXiv.llm.ollama import OllamaClient
from aiXiv.arxiv.arxiv import fetch_from_arxiv, fetch_from_arxiv_by_ids, store_papers
from aiXiv.arxiv.categories import ArxivCategory

root_path = Path(__file__).parent.parent


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
app.mount("/static", StaticFiles(directory=str(root_path / "static")), name="static")
app.mount(
    "/katex",
    StaticFiles(directory=str(root_path / "node_modules" / "katex" / "dist")),
    name="katex",
)
app.mount(
    "/htmx",
    StaticFiles(directory=str(root_path / "node_modules" / "htmx.org" / "dist")),
    name="htmx",
)
templates = Jinja2Templates(directory=str(root_path / "templates"))
templates.env.filters["latex"] = latex_to_html
templates.env.filters["timeago"] = timeago

_icons_dir = root_path / "node_modules" / "lucide-static" / "icons"


@lru_cache
def icon(name: str) -> Markup:
    """Inline a lucide SVG so it inherits text color (stroke="currentColor")."""
    return Markup((_icons_dir / f"{name}.svg").read_text())


templates.env.globals["icon"] = icon


def library_context(
    session: SessionDep,
    profile: Profile,
    sort: str = "score",
    active_tab: str = "unranked",
):
    order = Score.score.desc() if sort == "score" else Score.updated_at.desc()
    votes = {
        v.paper_id: v.score
        for v in session.exec(select(Vote).where(Vote.profile_id == profile.id)).all()
    }
    ranked = session.exec(
        select(Score, Paper)
        .join(Paper)
        .where(Score.profile_id == profile.id)
        .order_by(order)
    ).all()
    unranked = session.exec(
        select(Paper)
        .join(Library, Library.paper_id == Paper.id)
        .outerjoin(
            Score,
            (Score.paper_id == Paper.id) & (Score.profile_id == profile.id),
        )
        .where(Library.profile_id == profile.id, Score.id == None)  # noqa: E711
        .order_by(Paper.published_at.desc())
    ).all()
    return {
        "profile": profile,
        "ranked": ranked,
        "unranked": unranked,
        "votes": votes,
        "sort": sort,
        "active_tab": active_tab,
    }


def library_response(
    request: Request,
    session: SessionDep,
    profile_id: int,
    active_tab: str = "unranked",
    sort: str = "score",
):
    """Re-render the library partial — the response shape most routes share."""
    profile = session.get(Profile, profile_id)
    return templates.TemplateResponse(
        request, "_library.html", library_context(session, profile, sort, active_tab)
    )


def purge_papers(session: SessionDep, profile_id: int, paper_ids: list[int]):
    """Remove a profile's rows (library link, score, vote, bookmark) for given papers."""
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
    for model in (Score, Vote, Bookmark, Library):
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
    total_pages = max(1, math.ceil(total / per_page))
    return {
        "papers": papers,
        "imported": imported,
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
    sort: str = "score",
    active_tab: str = "unranked",
):
    profile = session.get(Profile, profile_id)
    return templates.TemplateResponse(
        request,
        "_library.html",
        library_context(session, profile, sort, active_tab),
    )


@app.post("/digest/rank")
async def rank_route(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_ids: list[int] = Form([]),
):
    profile = session.get(Profile, profile_id)
    if paper_ids:
        papers = session.exec(select(Paper).where(Paper.id.in_(paper_ids))).all()
        await rank_papers(profile, papers, session)
    return library_response(request, session, profile_id, active_tab="ranked")


@app.post("/scores/delete")
async def delete_score(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
):
    score = session.exec(
        select(Score).where(Score.profile_id == profile_id, Score.paper_id == paper_id)
    ).first()
    if score:
        session.delete(score)
        session.commit()
    return library_response(request, session, profile_id, active_tab="ranked")


@app.post("/library/remove-selected")
async def remove_selected_from_library(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_ids: list[int] = Form([]),
    active_tab: str = Form("unranked"),
):
    """Remove one or many papers from the library (a single card sends one id)."""
    purge_papers(session, profile_id, paper_ids)
    return library_response(request, session, profile_id, active_tab=active_tab)


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
    return Response(status_code=204)


@app.post("/votes/delete")
async def delete_vote(
    request: Request,
    session: SessionDep,
    profile_id: int = Form(...),
    paper_id: int = Form(...),
    active_tab: str = Form("ranked"),
):
    existing = session.exec(
        select(Vote).where(Vote.profile_id == profile_id, Vote.paper_id == paper_id)
    ).first()
    if existing:
        session.delete(existing)
        session.commit()
    return library_response(request, session, profile_id, active_tab=active_tab)
