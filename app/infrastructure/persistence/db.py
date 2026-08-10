"""Database engine management.

When ECON_DATABASE_URL / DATABASE_URL is set, that PostgreSQL instance is
used directly. When unset, a local embedded PostgreSQL cluster is started
from the repo's micromamba toolchain (data/pgdata, unix-socket only) —
real PostgreSQL, zero external services.
"""

import atexit
import logging
import os
import subprocess
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker | None = None

DB_NAME = "econboard"


def _pg_bin_dir(settings: Settings) -> Path:
    override = os.environ.get("ECON_PG_BIN_DIR")
    if override:
        return Path(override)
    return settings.repo_root / ".mamba" / "envs" / "toolchain" / "bin"


def _socket_dir(settings: Settings) -> Path:
    # Unix socket paths are limited to ~104 chars on macOS; the repo path is
    # long, so keep sockets in a short per-user tmp dir.
    d = Path(f"/tmp/econboard-pg-{os.getuid()}")
    d.mkdir(mode=0o700, exist_ok=True)
    return d


def start_embedded_postgres(settings: Settings | None = None) -> str:
    """Init (if needed) and start the embedded cluster; returns a DB URL."""
    settings = settings or get_settings()
    bin_dir = _pg_bin_dir(settings)
    initdb, pg_ctl, psql = bin_dir / "initdb", bin_dir / "pg_ctl", bin_dir / "psql"
    if not initdb.exists():
        raise RuntimeError(
            f"Embedded PostgreSQL tools not found at {bin_dir}. "
            "Run scripts/bootstrap.sh, or set DATABASE_URL to an existing PostgreSQL."
        )

    pgdata = settings.pgdata_dir
    sockdir = _socket_dir(settings)
    if not (pgdata / "PG_VERSION").exists():
        pgdata.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing embedded PostgreSQL cluster at %s", pgdata)
        subprocess.run(
            [str(initdb), "-D", str(pgdata), "-U", "postgres", "-A", "trust", "-E", "UTF8"],
            check=True, capture_output=True,
        )

    status = subprocess.run(
        [str(pg_ctl), "-D", str(pgdata), "status"], capture_output=True
    )
    if status.returncode != 0:  # not running
        logger.info("Starting embedded PostgreSQL (socket dir %s)", sockdir)
        subprocess.run(
            [
                str(pg_ctl), "-D", str(pgdata), "-w", "-t", "60",
                "-l", str(pgdata / "postgres.log"),
                "-o", f"-c listen_addresses='' -k {sockdir}",
                "start",
            ],
            check=True, capture_output=True,
        )
        atexit.register(stop_embedded_postgres, settings)

    # ensure the application database exists
    for attempt in range(10):
        check = subprocess.run(
            [str(psql), "-h", str(sockdir), "-U", "postgres", "-d", "postgres",
             "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'"],
            capture_output=True, text=True,
        )
        if check.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Embedded PostgreSQL did not become ready: {check.stderr}")
    if check.stdout.strip() != "1":
        subprocess.run(
            [str(psql), "-h", str(sockdir), "-U", "postgres", "-d", "postgres",
             "-c", f'CREATE DATABASE "{DB_NAME}"'],
            check=True, capture_output=True,
        )

    return f"postgresql+psycopg://postgres@/{DB_NAME}?host={sockdir}"


def stop_embedded_postgres(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    pg_ctl = _pg_bin_dir(settings) / "pg_ctl"
    if pg_ctl.exists() and (settings.pgdata_dir / "PG_VERSION").exists():
        subprocess.run(
            [str(pg_ctl), "-D", str(settings.pgdata_dir), "-m", "fast", "stop"],
            capture_output=True,
        )


def resolve_database_url(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    url = settings.database_url or os.environ.get("DATABASE_URL")
    if url:
        return url
    return start_embedded_postgres(settings)


def get_engine(url: str | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(url or resolve_database_url(), pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def open_session() -> Session:
    return get_session_factory()()


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
