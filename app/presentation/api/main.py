"""FastAPI application: lifespan boots the DB (migrations), builds the
context, recovers orphaned runs, and starts the single worker thread."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.application.context import build_default_context
from app.application.orchestrator import SimulationOrchestrator
from app.application.worker import SimulationWorker
from app.presentation.api.deps import ApiState, set_state
from app.presentation.api.routes import router

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    from app.config.settings import get_settings

    cfg = Config(str(get_settings().repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(get_settings().repo_root / "migrations"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    ctx = build_default_context()
    orchestrator = SimulationOrchestrator(ctx)
    worker = SimulationWorker(orchestrator)
    worker.recover_orphans()
    worker.start()
    set_state(ApiState(ctx=ctx, orchestrator=orchestrator, worker=worker))
    logger.info("AI Economic Board API ready")
    yield
    worker.stop()


app = FastAPI(title="AI Economic Board", version="0.1.0", lifespan=lifespan)
app.include_router(router)
