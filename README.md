# Industry News → LinkedIn Draft Automator

$0/month serverless stack that:

1. Runs daily via **GitHub Actions** (cron `0 6 * * *` UTC ≈ **07:00 CET**)
2. Searches industry news with **Exa.ai** (or **Tavily**)
3. Filters spam / engagement bait and keeps a SimCorp-safe Top 10 in **Neon Postgres**
4. Drafts **3** positive LinkedIn posts with **Grok** or **Claude**
5. Lets you approve/edit/publish in a **Streamlit** UI via LinkedIn OAuth 2.0

## Architecture

| Layer | Choice |
|-------|--------|
| UI | Streamlit Community Cloud |
| Cron | GitHub Actions |
| DB | Neon Serverless PostgreSQL (**no SQLite**) |
| Search | Exa.ai / Tavily |
| LLM | Grok (xAI) or Claude |
| Publish | LinkedIn REST (`ugcPosts`) + OAuth refresh token in Neon |
| Alerts | Slack/Discord webhook on failure or empty filter day |

## Locked product decisions

- **Draft style:** conversational leadership body + **3–5 hashtags at the end only**
- **Empty day:** skip drafts, send webhook — do **not** recycle yesterday’s Top 10
- **Tone:** tech disruption empowers IBOR/ABOR and legacy AM ops; **zero conflict with SimCorp**

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill Neon pooled URL, API keys, APP_PASSWORD, WEBHOOK_URL
export DATABASE_URL=... # postgresql://app:...@ep-xxx-pooler..../neondb?sslmode=require
alembic upgrade head
streamlit run app/streamlit_app.py
```

Manual pipeline:

```bash
python -m src.pipeline.run_daily
```

## Neon connection pooling

Use the **pooled** Neon host (`-pooler`) and SQLAlchemy **`NullPool`** (see `src/db/engine.py`) so Streamlit + Actions do not leak ghost connections.

```
DATABASE_URL=postgresql://app:SECRET@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require
```

Create a least-privilege `app` role (DML only) — see [`migrations/sql/least_privilege_role.sql`](migrations/sql/least_privilege_role.sql).

Because Streamlit Community Cloud IPs are dynamic, Neon typically allows `0.0.0.0/0`. Harden with: strong password, `sslmode=require`, least-privilege role, Streamlit `APP_PASSWORD`, and parameterized ORM only.

## GitHub Actions secrets

Set repository secrets used by [`.github/workflows/daily_pipeline.yml`](.github/workflows/daily_pipeline.yml):

`DATABASE_URL`, `EXA_API_KEY` (or `TAVILY_API_KEY` + `SEARCH_PROVIDER`), `GROK_API_KEY` or `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `WEBHOOK_URL`, optional model/base overrides.

## Streamlit Community Cloud

- Entry file: `app/streamlit_app.py`
- Mirror the same secrets in Streamlit **Secrets**
- **Sleep metric:** free apps hibernate after **7 consecutive days of zero traffic**. Optional mitigation: a free weekly cron HTTP ping to your public app URL.

## LinkedIn OAuth

1. Create a LinkedIn developer app with `openid`, `profile`, `w_member_social`
2. Set redirect URI to your Streamlit URL (and local `http://localhost:8501/` for dev)
3. In the UI **Settings** tab, click **Connect LinkedIn**
4. Refresh token (~365 days) is stored in `linkedin_tokens` (singleton row)

## Testing (no live API credits)

```bash
pytest -q -m "not integration"
```

All default tests mock Exa/Tavily/LLM/LinkedIn/webhooks via **pytest-mock**.

Optional Neon integration:

```bash
export TEST_DATABASE_URL='postgresql://...'
pytest -q -m integration
```

## Project layout

See `src/` for pipeline, search, LLM, LinkedIn, DB, and notify modules; `app/streamlit_app.py` for the approval UI; `migrations/` for Alembic + role SQL.
