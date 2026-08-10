import os
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]


def _admin_url() -> str | None:
    """URL of a PostgreSQL to run tests against, or None to skip DB tests."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    try:
        from app.infrastructure.persistence.db import resolve_database_url
        return resolve_database_url()
    except Exception:
        return None


@pytest.fixture(scope="session")
def test_db_url():
    admin = _admin_url()
    if admin is None:
        pytest.skip("No PostgreSQL available (run scripts/bootstrap.sh or set DATABASE_URL)")
    # carve out a dedicated test database next to the main one
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    testdb = "econboard_test"
    with engine.connect() as c:
        exists = c.execute(
            text("select 1 from pg_database where datname=:n"), {"n": testdb}
        ).scalar()
        if not exists:
            c.execute(text(f'CREATE DATABASE "{testdb}"'))
    engine.dispose()
    # swap the database name in the URL
    from sqlalchemy.engine import make_url
    url = make_url(admin).set(database=testdb)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def db_engine(test_db_url):
    from app.infrastructure.persistence.models import Base
    engine = create_engine(test_db_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Function-scoped session; truncates all tables afterwards."""
    from app.infrastructure.persistence.models import Base
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()
    with db_engine.connect() as c:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        c.commit()


@pytest.fixture()
def session_factory(db_engine):
    from app.infrastructure.persistence.models import Base
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    yield factory
    with db_engine.connect() as c:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        c.commit()
