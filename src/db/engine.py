"""SQLAlchemy engine with NullPool for Neon serverless + PgBouncer."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.config import get_settings, require_database_url

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure_sslmode(url: str) -> str:
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def get_engine(database_url: str | None = None, *, force_new: bool = False) -> Engine:
    """Return a process-wide engine using NullPool (no ghost connections)."""
    global _engine, _SessionLocal
    if _engine is not None and not force_new and database_url is None:
        return _engine

    url = _ensure_sslmode(database_url or require_database_url(get_settings()))
    engine = create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        future=True,
    )
    if force_new or database_url is not None:
        return engine

    _engine = engine
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    return _engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if database_url is not None:
        engine = get_engine(database_url, force_new=True)
        return sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    """Short-lived session; always closes (NullPool drops the connection)."""
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(database_url: str | None = None) -> bool:
    with session_scope(database_url) as session:
        session.execute(text("SELECT 1"))
    return True


def reset_engine() -> None:
    """Dispose cached engine (useful in tests / Streamlit reruns)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
