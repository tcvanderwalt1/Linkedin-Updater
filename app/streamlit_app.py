"""Streamlit approval UI for LinkedIn draft automation."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Streamlit Cloud runs this file from app/; ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from src.config import clear_settings_cache, get_settings
from src.db.engine import session_scope
from src.db.models import DraftStatus
from src.db.repository import Repository
from src.linkedin.oauth import (
    LinkedInOAuthError,
    build_authorize_url,
    exchange_code_for_tokens,
    fetch_member_urn,
    token_expiry_from_response,
)
from src.linkedin.publisher import LinkedInPublishError, publish_draft
from src.notify.webhook import notify_failure


@dataclass(frozen=True)
class DraftView:
    id: uuid.UUID
    status: str
    body: str
    model_name: str
    article_title: str


@dataclass(frozen=True)
class ArticleView:
    title: str
    url: str
    quality_score: float
    topics: str
    snippet: str


def _check_password() -> bool:
    settings = get_settings()
    expected = (settings.app_password or "").strip()
    if not expected:
        st.error("APP_PASSWORD is not configured in secrets.")
        return False
    if st.session_state.get("authenticated"):
        return True
    st.title("LinkedIn Updater")
    st.caption("Enter the app password to continue.")
    password = st.text_input("Password", type="password")
    if st.button("Sign in"):
        if password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def _handle_oauth_callback() -> None:
    params = st.query_params
    code = params.get("code")
    if not code:
        return
    if st.session_state.get("oauth_handled_code") == code:
        return
    try:
        payload = exchange_code_for_tokens(str(code))
        access_expires, refresh_expires = token_expiry_from_response(payload)
        member_urn = fetch_member_urn(payload["access_token"])
        with session_scope() as session:
            repo = Repository(session)
            repo.upsert_linkedin_token(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token") or "",
                access_expires_at=access_expires,
                refresh_expires_at=refresh_expires,
                member_urn=member_urn,
            )
        st.session_state["oauth_handled_code"] = code
        st.success("LinkedIn connected successfully.")
        st.query_params.clear()
    except (LinkedInOAuthError, Exception) as exc:
        st.error(f"OAuth failed: {exc}")


def _pipeline_status_panel() -> None:
    st.subheader("Latest pipeline run")
    try:
        with session_scope() as session:
            repo = Repository(session)
            run = repo.latest_pipeline_run()
            if run is None:
                st.info("No pipeline runs yet.")
                return
            payload = {
                "status": run.status,
                "started_at": str(run.started_at),
                "finished_at": str(run.finished_at) if run.finished_at else None,
                "articles_saved": run.articles_saved,
                "drafts_created": run.drafts_created,
                "error_message": run.error_message,
            }
        st.write(payload)
    except Exception as exc:
        st.warning(f"Could not load pipeline status: {exc}")


def _articles_today() -> None:
    st.subheader("Today's articles")
    try:
        with session_scope() as session:
            repo = Repository(session)
            articles = [
                ArticleView(
                    title=a.title,
                    url=a.url,
                    quality_score=float(a.quality_score),
                    topics=a.topics or "",
                    snippet=a.snippet or "",
                )
                for a in repo.articles_for_date(date.today())
            ]
    except Exception as exc:
        st.warning(f"Could not load articles: {exc}")
        return

    if not articles:
        st.info("No articles stored for today.")
        return
    for article in articles:
        st.markdown(
            f"**[{article.title}]({article.url})**  \n"
            f"Score: {article.quality_score:.2f} · Topics: `{article.topics}`  \n"
            f"{article.snippet[:280]}"
        )
        st.divider()


def _drafts_panel() -> None:
    st.subheader("Drafts")
    try:
        with session_scope() as session:
            repo = Repository(session)
            # Copy fields inside the open session to avoid DetachedInstanceError
            drafts = [
                DraftView(
                    id=d.id,
                    status=d.status,
                    body=d.body,
                    model_name=d.model_name or "",
                    article_title=(
                        d.article.title if d.article is not None else "Unknown article"
                    ),
                )
                for d in repo.list_drafts(limit=30)
            ]
    except Exception as exc:
        st.warning(f"Could not load drafts: {exc}")
        return

    if not drafts:
        st.info("No drafts yet.")
        return

    for draft in drafts:
        with st.expander(
            f"{draft.status.upper()} · {draft.article_title}",
            expanded=draft.status == "pending",
        ):
            st.caption(f"Draft ID: `{draft.id}` · Model: `{draft.model_name}`")
            body_key = f"body_{draft.id}"
            new_body = st.text_area("Post body", value=draft.body, key=body_key, height=220)
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("Save edits", key=f"save_{draft.id}"):
                with session_scope() as session:
                    Repository(session).update_draft_body(draft.id, new_body)
                st.success("Saved.")
                st.rerun()
            if c2.button("Approve", key=f"approve_{draft.id}"):
                with session_scope() as session:
                    Repository(session).set_draft_status(
                        draft.id, DraftStatus.approved.value
                    )
                st.rerun()
            if c3.button("Reject", key=f"reject_{draft.id}"):
                with session_scope() as session:
                    Repository(session).set_draft_status(
                        draft.id, DraftStatus.rejected.value
                    )
                st.rerun()
            if c4.button("Publish to LinkedIn", key=f"publish_{draft.id}"):
                try:
                    with session_scope() as session:
                        urn = publish_draft(
                            Repository(session), draft.id, body=new_body
                        )
                    st.success(f"Published: {urn}")
                    st.rerun()
                except (LinkedInPublishError, LinkedInOAuthError, Exception) as exc:
                    notify_failure(str(exc), stage="linkedin_publish")
                    st.error(f"Publish failed: {exc}")


def _settings_panel() -> None:
    st.subheader("LinkedIn connection")
    try:
        with session_scope() as session:
            token = Repository(session).get_linkedin_token()
            token_view = None
            if token is not None:
                token_view = {
                    "member_urn": token.member_urn,
                    "access_expires_at": str(token.access_expires_at),
                    "refresh_expires_at": str(token.refresh_expires_at)
                    if token.refresh_expires_at
                    else None,
                }
        if token_view:
            st.success(f"Connected as `{token_view['member_urn']}`")
            st.caption(
                f"Access expires: {token_view['access_expires_at']} · "
                f"Refresh expires: {token_view['refresh_expires_at']}"
            )
        else:
            st.warning("LinkedIn is not connected.")
    except Exception as exc:
        st.warning(f"Token status unavailable: {exc}")

    try:
        url = build_authorize_url(state=str(uuid.uuid4()))
        st.link_button("Connect / reconnect LinkedIn", url)
    except LinkedInOAuthError as exc:
        st.error(str(exc))

    st.markdown(
        """
**Ops notes**
- Streamlit Community Cloud hibernates free apps after **7 consecutive days** of zero traffic.
- Optional: add a free weekly cron ping to this app URL to reduce sleep risk.
- Neon must allow `0.0.0.0/0`; protect with strong DB password, `sslmode=require`, least-privilege `app` role.
"""
    )


def main() -> None:
    st.set_page_config(page_title="LinkedIn Updater", page_icon="📰", layout="wide")
    clear_settings_cache()
    if not _check_password():
        return
    _handle_oauth_callback()
    st.title("Industry News → LinkedIn Drafts")
    st.caption(
        "Approve SimCorp-safe, forward-looking posts drafted from daily industry news."
    )
    tab_status, tab_articles, tab_drafts, tab_settings = st.tabs(
        ["Pipeline", "Articles", "Drafts", "Settings"]
    )
    with tab_status:
        _pipeline_status_panel()
    with tab_articles:
        _articles_today()
    with tab_drafts:
        _drafts_panel()
    with tab_settings:
        _settings_panel()


if __name__ == "__main__":
    main()
