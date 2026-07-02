<p align="center">
  <img src="https://raw.githubusercontent.com/haykh/aiXiv/2e6000604fed9069a2bbd2db100e407dd90084ce/aiXiv/static/icons/icon.svg" alt="aiXiv logo" width="96">
</p>

<h1 align="center">${\color{f27171}\textit{ai}}\text{Xiv}$</h1>
<p align="center">A personalized AI-driven arXiv digest driven by your own research profile.</p>

---

aiXiv reads a description of your research interests, builds an interest profile from it with an LLM, and uses that profile to rank recent arXiv abstracts by relevance to you. You can rate the rankings, and those ratings are fed back to the model to refine the profile over time.

## What it does

- **Builds a profile from free text.** Paste a bio, past abstracts, keywords, or anything describing what you work on. An LLM extracts a name, summary, and set of keywords, which are stored in a local database.
- **Fetches abstracts from arXiv.** Browse any arXiv category (e.g. `astro-ph.HE`) over a chosen date range and import the results into a library.
- **Ranks papers by relevance.** The model scores each imported paper against your profile (0–10) and gives a short reason for the score.
- **Lets you vote.** Rate any ranked paper 0–10 with a slider. Once you have votes, a "refine from votes" action feeds them back to the model to update your profile.
- **Bookmarks.** Save papers to a separate bookmarked list from either the ranked or unranked views.
- **Multiple profiles.** Keep several profiles and switch between them; each has its own rankings, votes, and bookmarks.
- **Math rendering.** Titles and abstracts render LaTeX via KaTeX.

## How it works

1. **Create a profile** — click *+ new profile*, give it a name, and paste in text describing your interests. The model analyzes it and you save the resulting profile.
2. **Browse arXiv** — on the *browse arXiv* tab, pick a category and date range (or use the last-day / week / month presets) and import papers into your library.
3. **Rank** — in the *library* under *unranked*, select papers and click *rank selected*. Ranked papers move to the *ranked* tab with a relevance score and a one-line reason.
4. **Vote and refine** — click a paper's vote score to open a slider and rate it. When you have votes, use *refine from votes* to update the profile from your feedback.
5. **Bookmark** — use the bookmark control on any paper's card to save it to the *bookmarked* tab.

## Requirements

- Python 3.11+
- An LLM backend: a local [Ollama](https://ollama.com/) server, or a logged-in [Claude Code](https://code.claude.com/docs/en/overview) (`claude`) or [Codex](https://developers.openai.com/codex/cli/) (`codex`) CLI (see [Configuration](#configuration)).

## Install

```sh
uv tool install aixiv-digest 
# or
pip install aixiv-digest
```

## Running

```sh
aiXiv
# or to view options
aiXiv --help
```

Then open the URL it prints (by default <http://127.0.0.1:8000>).

| Flag             | Meaning                          |
| ---------------- | -------------------------------- |
| `--host`         | Host to bind the server to       |
| `--port`, `-p`   | Port to bind the server to       |
| `--db`, `-d`     | Path to the SQLite database file |

## Development

Running from a clone additionally needs Node.js/npm — the front-end assets (HTMX, KaTeX, Lucide icons) are vendored from `node_modules` into the package, and the stylesheet is compiled from Sass:

```sh
# 1. Python package (editable)
uv venv && source .venv/bin/activate
uv pip install -e .

# 2. Front-end assets (vendored copies are committed;
#    re-run after upgrading npm packages or editing scss/)
npm i
npm run vendor
npm run css

# 3. Dev server (auto-reload)
fastapi dev aiXiv/main.py
```

> `npm start` runs the Sass watcher and the dev server together.

## Configuration

LLM settings are managed in-app through the **settings** dialog (the gear icon in the top bar) and stored in the database. The relevant options are the provider, the model, and — for Ollama — the API URL.

Every LLM call logs two lines to the server console (`claude-cli ▶ requesting model=…` / `claude-cli ◀ answered by model=…`), reporting both the requested model and the model that actually answered, so you can verify the backend is using what you configured.

**Ollama (local).** Runs against a local Ollama server. Defaults live in [`aiXiv/settings.py`](aiXiv/settings.py):

| Setting        | Default                      |
| -------------- | ---------------------------- |
| Provider       | `ollama`                     |
| Model          | `gpt-oss:20b`                |
| Ollama API URL | `http://localhost:11434`     |

Point the API URL at your Ollama instance and pull a model beforehand (e.g. `ollama pull gpt-oss:20b`). The model dropdown lists whatever that server has installed.

> When accessing the Ollama instance running on Windows from the app running on WSL2, use `ip route | grep default | awk '{print $3}'` to determine the host (Windows) ip, and use that instead of the `localhost`.

**Claude CLI (subscription).** Shells out to a locally-installed, logged-in [Claude Code](https://code.claude.com/docs/en/overview) CLI (`claude -p`), so it uses your existing Claude subscription instead of an API key. The model field takes an alias (`sonnet`, `haiku`, `opus`) or a full model ID (`claude-opus-4-8`); leave it empty for the CLI's default.

**Codex CLI (subscription).** Same idea with the [Codex](https://developers.openai.com/codex/cli/) CLI (`codex exec`), using your ChatGPT login. The model dropdown is read from the model list codex itself caches (`~/.codex/models_cache.json`); run `codex` once if it's empty.

> The CLI backends are experimental and meant for testing. They spawn one CLI process per request (a ranking run takes several seconds per paper), usage counts against your subscription limits, and driving coding agents this way is an off-label use of those tools.

**Claude / OpenAI (API).** These providers appear in the settings dialog but are disabled — the client classes are not implemented yet. Using them requires both the corresponding client code and an API key with billing from the provider's developer console.

## Project layout

```
aiXiv/
  main.py            FastAPI app: routes, page rendering, CLI entry point
  settings.py        default settings and LLM prompts
  arxiv/             arXiv fetching and category list
  database/          SQLModel tables and DB setup/migrations
  llm/               LLM abstraction (base, ollama, cli) + profile/paper logic
  utils/             LaTeX-to-HTML and "time ago" helpers
  templates/         Jinja2 templates (HTMX-driven fragments)
  static/            compiled CSS + vendored front-end assets
scss/                Sass sources (compiled into aiXiv/static/css)
```

## Tech stack

FastAPI, SQLModel/SQLite, Jinja2, and HTMX on the back end; Pico CSS (via Sass), KaTeX, and Lucide icons on the front end.
