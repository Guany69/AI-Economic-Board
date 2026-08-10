"""End-to-end tests: HTTP API -> orchestrator -> worker -> PostgreSQL,
with fake model runners (the real-model path is exercised by
tests/end_to_end/test_real_models.py under -m real_models).
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.context import AppContext
from app.application.orchestrator import SimulationOrchestrator
from app.application.worker import SimulationWorker
from app.business.comparison import MetricComparisonService
from app.business.routing import ChangeRouter
from app.business.validation import ChangeValidator
from app.config.loader import get_variable_registry
from app.config.settings import get_settings
from app.infrastructure.adapters.tax_to_fair import ConfiguredTaxToFairAdapter
from app.infrastructure.llm.client import AnthropicInterpreter
from app.presentation.api.deps import ApiState, set_state
from app.presentation.api.routes import router
from tests.fakes import FakeFairRunner, FakeInterpreter, FakeTaxRunner, make_metrics


@pytest.fixture()
def api(session_factory, tmp_path, monkeypatch):
    """TestClient wired to fake models + real DB; returns (client, ctx)."""
    registry = get_variable_registry()
    ctx = AppContext(
        settings=get_settings(),
        registry=registry,
        validator=ChangeValidator(registry),
        router=ChangeRouter(registry),
        comparison=MetricComparisonService(),
        fair_runner=FakeFairRunner(),
        tax_runner=FakeTaxRunner(),
        tax_adapter=ConfiguredTaxToFairAdapter(),
        interpreter=FakeInterpreter(),
        session_factory=session_factory,
    )
    orchestrator = SimulationOrchestrator(ctx)
    worker = SimulationWorker(orchestrator)
    worker.start()
    set_state(ApiState(ctx=ctx, orchestrator=orchestrator, worker=worker))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    yield client, ctx
    worker.stop()


@pytest.fixture()
def seeded_baseline(session_factory, tmp_path):
    from app.domain.enums import ModelName
    from app.infrastructure.persistence.repositories import (
        ArtifactRepository, BaselineRepository, ModelVersionRepository,
    )
    snap = tmp_path / "BASE.BIN"
    snap.write_bytes(b"fake snapshot")
    with session_factory() as s:
        fair_id = ModelVersionRepository(s).get_or_create(ModelName.FAIR, "fake-fair", {})
        art_id = ArtifactRepository(s).register(fair_id, "BASE.BIN", str(snap), "0" * 64, 13)
        bl = BaselineRepository(s)
        bid = bl.create("fake-baseline", fair_id, "2026Q3", "2029Q4", art_id)
        bl.add_metrics(bid, make_metrics())
        s.commit()
    return bid


def _wait_terminal(client, run_id, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/simulations/{run_id}").json()
        if data["status"] in ("COMPLETED", "FAILED"):
            return data
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not finish")


def test_health_and_variables(api):
    client, _ = api
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    variables = client.get("/api/v1/variables").json()
    assert {v["id"] for v in variables} >= {"COG", "II_rt_all", "CTC_c", "RS"}


def test_case_a_direct_fair_via_api(api, seeded_baseline):
    client, ctx = api
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "COG", "change": {"type": "ABSOLUTE", "value": 25},
    })
    assert resp.status_code == 202
    run_id = resp.json()["simulation_run_id"]
    data = _wait_terminal(client, run_id)
    assert data["status"] == "COMPLETED"
    assert data["change"]["model_route"] == "DIRECT_FAIR"
    assert len(data["metric_deltas"]) == 140
    assert data["interpretation"]["response_text"]
    assert "tax_calculator_result" not in data          # taxcalc did not run
    assert ctx.tax_runner.calls == []


def test_case_b_tax_path_via_api(api, seeded_baseline):
    client, _ = api
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "II_rt_all", "change": {"type": "ABSOLUTE", "value": -0.02},
    })
    assert resp.status_code == 202
    data = _wait_terminal(client, resp.json()["simulation_run_id"])
    assert data["status"] == "COMPLETED"
    assert data["tax_calculator_result"]["taxcalc_version"] == "6.7.3"
    adapter = data["tax_fair_adapter_result"]
    assert adapter["target_fair_variable"] == "D1G"
    assert len(adapter["quarterly_values"]) == 14
    assert len(data["metric_deltas"]) == 140


def test_case_c_invalid_variable_422(api, seeded_baseline):
    client, ctx = api
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "NOT_A_VAR", "change": {"type": "ABSOLUTE", "value": 1},
    })
    assert resp.status_code == 422
    assert ctx.fair_runner.calls == []

    resp = client.post("/api/v1/simulations", json={
        "variable_id": "II_rt_all", "change": {"type": "SET_VALUE", "value": 0.2},
    })
    assert resp.status_code == 422


def test_case_d_no_baseline_409(api):
    client, ctx = api
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "COG", "change": {"type": "ABSOLUTE", "value": 25},
    })
    assert resp.status_code == 409
    assert "baseline" in resp.json()["detail"].lower()
    assert ctx.fair_runner.calls == []


def test_case_f_unmapped_tax_variable_fails_explicitly(api, seeded_baseline):
    client, ctx = api
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "CTC_c", "change": {"type": "ABSOLUTE", "value": 500},
    })
    assert resp.status_code == 202                       # valid request; fails in workflow
    data = _wait_terminal(client, resp.json()["simulation_run_id"])
    assert data["status"] == "FAILED"
    assert data["error"]["type"] == "TaxToFairMappingError"
    assert "tax_calculator_result" not in data           # fail-fast: no taxcalc run
    assert ctx.tax_runner.calls == []


def test_case_h_real_interpreter_without_key(api, seeded_baseline, monkeypatch):
    """The REAL AnthropicInterpreter with no key: fails explicitly at the
    interpretation step; deterministic results are retained."""
    client, ctx = api
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx.interpreter = AnthropicInterpreter(ctx.settings)
    resp = client.post("/api/v1/simulations", json={
        "variable_id": "COG", "change": {"type": "ABSOLUTE", "value": 25},
    })
    data = _wait_terminal(client, resp.json()["simulation_run_id"])
    assert data["status"] == "FAILED"
    assert data["error"]["type"] == "MissingApiKeyError"
    assert len(data["metric_deltas"]) == 140             # deterministic results retained
    assert "interpretation" not in data


def test_unknown_run_404(api):
    client, _ = api
    resp = client.get("/api/v1/simulations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
