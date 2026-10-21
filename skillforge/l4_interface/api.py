"""FastAPI 接入：POST /generate、GET /sessions/{id}、GET /healthz。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    request: str = Field(..., description="用户原始请求，如“帮我写开题报告”")
    skill: str | None = Field(None, description="可选：直接指定技能，跳过路由")
    collected: dict[str, str] = Field(default_factory=dict)
    out_path: Path | None = Field(None, description="docx 输出路径；不传则只返回草稿")


class GenerateResponse(BaseModel):
    status: str
    session_id: str | None = None
    skill: str | None = None
    gate: dict[str, Any] | None = None
    failures: list[dict[str, Any]] | None = None
    missing: list[str] | None = None
    output_path: str | None = None
    message: str | None = None


def create_app(llm=None):
    from fastapi import FastAPI, HTTPException

    from skillforge.l3_orchestration.orchestrator import Orchestrator
    from skillforge.shared.errors import SkillNotFound

    app = FastAPI(title="SkillForge", version="0.1.0")

    def _orchestrator() -> Orchestrator:
        if llm is None:
            raise HTTPException(503, "LLM 未配置：启动时传入 llm 实例")
        return Orchestrator.from_config(llm=llm)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/generate", response_model=GenerateResponse)
    def generate(req: GenerateRequest) -> GenerateResponse:
        try:
            result = _orchestrator().run(
                request=req.request,
                collected=req.collected,
                ask_fn=None,
                out_path=req.out_path,
            )
        except SkillNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(503, str(exc)) from exc

        return GenerateResponse(
            status=result["status"],
            session_id=result.get("session_id"),
            skill=result.get("skill"),
            gate=_gate_dict(result.get("gate")),
            failures=_failures(result.get("gate")),
            missing=result.get("missing"),
            output_path=result.get("output_path"),
            message=result.get("message"),
        )

    return app


def _gate_dict(gate) -> dict | None:
    if gate is None:
        return None
    return {"passed": gate.passed, "score": gate.score, "threshold": gate.threshold}


def _failures(gate) -> list[dict] | None:
    if gate is None or not gate.failures:
        return None
    return [
        {"rule": f.rule, "section": f.section, "evidence": f.evidence, "severity": f.severity}
        for f in gate.failures
    ]
