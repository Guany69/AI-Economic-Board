"""Thin HTTP client for the econ CLI."""

import time

import httpx


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def health(self) -> dict:
        return self._get("/api/v1/health")

    def variables(self) -> list[dict]:
        return self._get("/api/v1/variables")

    def submit(self, variable_id: str, change_type: str, value: str) -> dict:
        resp = self._client.post("/api/v1/simulations", json={
            "variable_id": variable_id,
            "change": {"type": change_type, "value": value},
        })
        if resp.status_code not in (200, 202):
            raise SystemExit(f"Submission rejected ({resp.status_code}): "
                             f"{resp.json().get('detail', resp.text)}")
        return resp.json()

    def result(self, run_id: str) -> dict:
        return self._get(f"/api/v1/simulations/{run_id}")

    def wait(self, run_id: str, poll_seconds: float = 2.0,
             timeout_seconds: float = 3600.0) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while True:
            data = self.result(run_id)
            if data["status"] in ("COMPLETED", "FAILED"):
                return data
            if time.monotonic() > deadline:
                raise SystemExit(f"Timed out waiting for run {run_id}")
            time.sleep(poll_seconds)

    def _get(self, path: str) -> dict:
        resp = self._client.get(path)
        if resp.status_code == 404:
            raise SystemExit(f"Not found: {resp.json().get('detail', path)}")
        resp.raise_for_status()
        return resp.json()
