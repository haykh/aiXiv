<p align="center">
  <img src="static/icons/icon.svg" alt="aiXiv logo" width="96">
</p>

<h1 align="center">${\color{f27171}\textit{ai}}\text{Xiv}$</h1>
<p align="center">A personalized arXiv digest driven by your own research profile.</p>

---

aiXiv reads a description of your research interests, builds an interest
profile from it with an LLM, and uses that profile to rank recent arXiv
abstracts by relevance to you. You can rate the rankings, and those ratings
are fed back to the model to refine the profile over time.

## What it does

- **Builds a profile from free text.** Paste a bio, past abstracts, keywords,
  or anything describing what you work on. An LLM extracts a name, summary, and
  set of keywords, which are stored in a local database.
- **Fetches abstracts from arXiv.** Browse any arXiv category (e.g.
  `astro-ph.HE`) over a chosen date range and import the results into a
  library.
- **Ranks papers by relevance.** The model scores each imported paper against
  your profile (0–10) and gives a short reason for the score.
- **Lets you vote.** Rate any ranked paper 0–10 with a slider. Once you have
  votes, a "refine from votes" action feeds them back to the model to update
  your profile.
- **Bookmarks.** Save papers to a separate bookmarked list from either the
  ranked or unranked views.
- **Multiple profiles.** Keep several profiles and switch between them; each
  has its own rankings, votes, and bookmarks.
- **Math rendering.** Titles and abstracts render LaTeX via KaTeX.

## How it works

1. **Create a profile** — click *+ new profile*, give it a name, and paste in
   text describing your interests. The model analyzes it and you save the
   resulting profile.
2. **Browse arXiv** — on the *browse arXiv* tab, pick a category and date range
   (or use the last-day / week / month presets) and import papers into your
   library.
3. **Rank** — in the *library* under *unranked*, select papers and click
   *rank selected*. Ranked papers move to the *ranked* tab with a relevance
   score and a one-line reason.
4. **Vote and refine** — click a paper's vote score to open a slider and rate
   it. When you have votes, use *refine from votes* to update the profile from
   your feedback.
5. **Bookmark** — use the bookmark control on any paper's card to save it to
   the *bookmarked* tab.

## Requirements

- Python 3.11+
- Node.js and npm (front-end libraries — HTMX, KaTeX, Lucide icons — are served
  from `node_modules`, and the stylesheet is compiled from Sass)
- An LLM backend. **[Ollama](https://ollama.com/) is the only backend currently
  wired up** (see [Configuration](#configuration)).

## Setup

```sh
# 1. Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Front-end dependencies (required — served at runtime from node_modules)
npm install

# 3. Build the stylesheet (a compiled static/style.css is committed;
#    run this after editing anything under scss/)
npm run css
```

## Running

```sh
fastapi dev aiXiv/main.py
```

Then open the URL it prints (by default <http://127.0.0.1:8000>). The SQLite
database is created automatically at `data/app.db` on first run.

## Configuration

LLM settings are managed in-app through the **settings** dialog (the gear icon
in the top bar) and stored in the database. The relevant options are the
provider, the model, and — for Ollama — the API URL.

**Ollama (local).** This is the working backend. Defaults live in
[`aiXiv/defaults.py`](aiXiv/defaults.py):

| Setting        | Default                      |
| -------------- | ---------------------------- |
| Provider       | `ollama`                     |
| Model          | `deepseek-r1:latest`         |
| Ollama API URL | `http://172.29.96.1:11434`   |

Point the API URL at your Ollama instance and pull a model beforehand (e.g.
`ollama pull deepseek-r1`). The default URL targets the Windows host gateway
from WSL2; a native install typically uses `http://localhost:11434`.

**Claude / OpenAI.** These providers appear in the settings dialog but are
disabled — the client classes are not implemented yet, so selecting them has no
effect. Using them requires both the corresponding client code and an API key
with billing from the provider's developer console.

## Project layout

```
aiXiv/
  main.py            FastAPI app: routes and page rendering
  defaults.py        default settings
  arxiv/             arXiv fetching and category list
  database/          SQLModel tables and DB setup/migrations
  llm/               LLM abstraction (base, ollama) + profile/paper logic
  utils/             LaTeX-to-HTML and "time ago" helpers
templates/           Jinja2 templates (HTMX-driven fragments)
scss/ + static/      Sass sources and compiled assets
data/                SQLite database (created on first run)
```

## Tech stack

FastAPI, SQLModel/SQLite, Jinja2, and HTMX on the back end; Pico CSS (via Sass),
KaTeX, and Lucide icons on the front end.
