"""Shared pytest fixtures.

Provides an in-memory SQLite engine with all tables created, plus helpers to
build a session and the FastAPI dependency overrides for ``get_db`` and
``get_current_user`` so endpoint tests run without Tailscale or a real DB.
"""

import os
import sys

import pytest

# Ensure the ``app`` package (backend/) is importable when running from the repo root.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  (registers all tables on the metadata)


def get_test_engine():
    """In-memory SQLite engine with all SQLModel tables, shared via StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def get_test_session(engine=None):
    if engine is None:
        engine = get_test_engine()
    return Session(engine)


@pytest.fixture
def engine():
    return get_test_engine()


@pytest.fixture
def session(engine):
    return get_test_session(engine)


@pytest.fixture
def owner(session):
    from app.models.user import User

    user = User(login="owner@example.test", name="Owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


__all__ = ["get_test_engine", "get_test_session"]
