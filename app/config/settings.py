"""Application settings (env prefix ECON_)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECON_", extra="ignore")

    # paths
    repo_root: Path = REPO_ROOT
    config_dir: Path = REPO_ROOT / "config"
    data_dir: Path = REPO_ROOT / "data"
    fair_model_dir: Path = REPO_ROOT / "FMFP"
    fp_binary: Path = REPO_ROOT / "data" / "artifacts" / "fair" / "bin" / "fp"
    fair_runtime_dir: Path = REPO_ROOT / "data" / "runtime" / "fair"
    fair_artifacts_dir: Path = REPO_ROOT / "data" / "artifacts" / "fair"
    pgdata_dir: Path = REPO_ROOT / "data" / "pgdata"

    # database: when unset, an embedded pgserver instance is started
    database_url: str | None = None

    # simulation
    solve_start: str = "2026Q3"
    solve_end: str = "2029Q4"
    horizon_quarters: int = 14
    fair_timeout_seconds: int = 600
    taxcalc_timeout_seconds: int = 1800
    taxcalc_year: int = 2026

    # LLM
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 2000

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
