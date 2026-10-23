"""Orchestrator 日志：trace_id 贯通、关键阶段事件存在。"""

from __future__ import annotations

import io
import json
import logging

import pytest
from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.shared.logger import JsonFormatter
from skillforge.shared.types import GateResult, RouteDecision


@pytest.fixture
def capture_l3():
    stream = io.StringIO()
    logger = logging.getLogger("skillforge.l3")
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel("INFO")
    logger.propagate = False
    yield stream
    logger.handlers.clear()


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in stream.getvalue().strip().splitlines() if ln]


def _always_pass() -> GateResult:
    return GateResult(passed=True, score=1.0, threshold=0.8, failures=[])


def test_full_run_logs_trace_id_and_events(monkeypatch, capture_l3):
    class FakeLLM:
        def complete(self, prompt: str) -> str:
            return "正文"

    orch = Orchestrator.from_config(llm=FakeLLM())

    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _always_pass())
    monkeypatch.setattr(orch.renderer, "render", lambda draft, out: out)
    monkeypatch.setattr(
        orch.queue,
        "generate_all",
        lambda skill, collected: {s: "正文" for s in skill.contract.sections},
    )

    contract = orch.loader.load_contract("test-skill")
    collected = {f: f"value-{f}" for f in contract.required_fields}

    result = orch.run(request="任意", collected=collected, trace_id="")
    assert result["status"] == "delivered"

    records = _lines(capture_l3)
    events = {r["message"] for r in records}
    assert {
        "route.decided",
        "generate.start",
        "generate.done",
        "gate.round",
        "run.delivered",
    } <= events

    trace_ids = {r.get("trace_id") for r in records}
    assert len(trace_ids) == 1
    assert all(isinstance(t, str) and t for t in trace_ids)


def test_clarification_logged(monkeypatch, capture_l3):
    orch = Orchestrator.from_config(llm=None)
    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(
            skill=None,
            confidence=0.0,
            needs_clarification=True,
        ),
    )
    orch.run(request="x", collected={}, trace_id="")
    records = _lines(capture_l3)
    assert any(r["message"] == "route.clarify" for r in records)
    assert all(r.get("trace_id") for r in records)


def test_explicit_trace_id_propagates(monkeypatch, capture_l3):
    orch = Orchestrator.from_config(llm=None)
    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(
            skill=None,
            confidence=0.0,
            needs_clarification=True,
        ),
    )
    orch.run(request="x", collected={}, trace_id="fixed-trace")
    records = _lines(capture_l3)
    assert records
    assert all(r["trace_id"] == "fixed-trace" for r in records)
