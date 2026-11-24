"""Point the test run at a separate, freshly cleaned database so tests never touch development data."""

import hashlib
import os
import re

import psycopg
import pytest

DEV_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://rera:rera@localhost:5432/rera?sslmode=require")
TEST_DB = "rera_test"
_base, _, _query = DEV_URL.partition("?")  # keep ?sslmode=require: the database only accepts TLS connections
TEST_URL = _base.rsplit("/", 1)[0] + f"/{TEST_DB}" + (f"?{_query}" if _query else "")

# Must run before any `app` import: settings and the SQLAlchemy engine read these at import time.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["RERANKER"] = "none"          # no model download in tests
os.environ["KB_QUERY_REWRITE"] = "true"
os.environ["OPENAI_API_KEY"] = "sk-test-unused"  # LLM calls are stubbed per test; this only passes the up-front check
os.environ["DATA_ENCRYPTION_KEY"] = "dGVzdC1zdWl0ZS1rZXktbm90LWZvci1yZWFsLXVzZSE="  # fixed 32-byte test key

with psycopg.connect(DEV_URL.replace("+psycopg", ""), autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session", autouse=True)
def clean_database():
    from sqlalchemy import text

    from app.db import engine, init_db
    init_db()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE projects, audit_log, kb_documents, kb_embedding_cache, users, system_settings, llm_calls, "
                          "retrieval_log, evaluation_runs RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM checkpoint_writes; DELETE FROM checkpoint_blobs; DELETE FROM checkpoints"))
    from app.catalog.loader import get_catalog
    from app.db import SessionLocal
    from app.security.auth import create_user
    with SessionLocal.begin() as session:  # the principal functional tests act as (holds every role)
        TESTER["id"] = create_user(session, "tester", "Test User", "Tester-Password-1",
                                   [r.id for r in get_catalog().roles] + ["admin"]).id
    from app import ops  # functional tests exercise the assisted (post-evaluation) stage; step-20 tests change it
    ops.set_setting("deployment", {"stage": "assisted", "require_current_evaluation": False}, "tests")
    yield


TESTER: dict = {}


@pytest.fixture(autouse=True)
def signed_in(request, monkeypatch):
    """Functional tests act as a signed-in, MFA-verified user holding every role. Tests marked `real_auth`
    (tests/test_security_platform.py) go through real sign-in, MFA and RBAC instead."""
    if request.node.get_closest_marker("real_auth"):
        return
    from app.catalog.loader import get_catalog
    from app.security import rbac
    principal = rbac.Principal(TESTER["id"], "tester", "Test User", [r.id for r in get_catalog().roles] + ["admin"], True)
    monkeypatch.setattr(rbac, "authenticate_request", lambda _request: principal)


def fake_embed(text: str) -> list[float]:
    """Deterministic bag-of-words embedding: texts sharing words get high cosine similarity."""
    dim = int(os.environ.get("EMBEDDING_DIM", "384"))
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@pytest.fixture
def fake_embeddings(monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "embed", fake_embed)
    monkeypatch.setattr(llm, "embed_many", lambda texts: [fake_embed(t) for t in texts])
