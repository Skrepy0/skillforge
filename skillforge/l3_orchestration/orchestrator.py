"""主协调器：把路由、会话、生成、门禁、重写、渲染串成完整流程。"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from skillforge.l1_governance.gate_runner import GateRunner
from skillforge.l2_capability.loader import Loader
from skillforge.l2_capability.renderer.docx_renderer import DocxRenderer
from skillforge.l2_capability.sanitize import filter_collected
from skillforge.l3_orchestration.contract import missing_fields
from skillforge.l3_orchestration.fallback import Fallback
from skillforge.l3_orchestration.rewrite import Rewriter
from skillforge.l3_orchestration.router import Router
from skillforge.l3_orchestration.session import SessionManager
from skillforge.l3_orchestration.state_machine import StateMachine
from skillforge.l3_orchestration.task_queue import LLMClient, TaskQueue
from skillforge.shared.config import AppConfig, load_config
from skillforge.shared.errors import RenderError
from skillforge.shared.logger import get_logger
from skillforge.shared.types import DraftDocument


class _MissingLLM:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError("未注入 LLMClient：请在 Orchestrator.from_config(llm=...) 传入")


class Orchestrator:
    def __init__(self, config: AppConfig, llm: LLMClient) -> None:
        self.config = config
        self.logger = get_logger("skillforge.l3", config.logging)
        self.loader = Loader(config.skills_root)
        self.router = Router(config.routing)
        self.sessions = SessionManager()
        self.fsm = StateMachine()
        self.queue = TaskQueue(llm, config.settings.queue_concurrency)
        self.rewriter = Rewriter(llm)
        self.gates = GateRunner(config.gates)
        self.renderer = DocxRenderer()
        self.fallback = Fallback()

    @classmethod
    def from_config(cls, llm: LLMClient | None = None) -> Orchestrator:
        return cls(load_config(), llm or _MissingLLM())

    def run(
        self,
        request: str,
        collected: dict[str, str] | None = None,
        ask_fn: Callable[[list[str]], dict[str, str]] | None = None,
        out_path: Path | None = None,
        trace_id: str = "",
    ) -> dict:
        if not trace_id:
            trace_id = uuid.uuid4().hex

        decision = self.router.route(request)
        self.logger.info(
            "route.decided",
            extra={
                "trace_id": trace_id,
                "layer": "l3",
                "skill": decision.skill,
                "confidence": decision.confidence,
                "candidates": len(decision.candidates),
            },
        )

        if decision.needs_clarification or decision.skill is None:
            self.logger.info(
                "route.clarify",
                extra={
                    "trace_id": trace_id,
                    "layer": "l3",
                    "candidates": [name for name, _ in decision.candidates],
                },
            )
            return self.fallback.clarify(decision)

        skill = self.loader.load(decision.skill)
        contract = skill.contract

        session = self.sessions.create(decision.skill)
        self.sessions.merge(session, filter_collected(contract, collected or {}))

        missing = missing_fields(contract, session.collected)
        if missing:
            if ask_fn is None:
                self.logger.info(
                    "collect.missing",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l3",
                        "missing": missing,
                    },
                )
                return {**self.fallback.needs_input(missing), "session_id": session.session_id}

            self.logger.info(
                "collect.missing",
                extra={
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "layer": "l3",
                    "missing": missing,
                    "interactive": True,
                },
            )
            answers = self.fallback.ask(missing, ask_fn)
            self.sessions.merge(session, filter_collected(contract, answers))
            missing = missing_fields(contract, session.collected)
            if missing:
                self.logger.info(
                    "collect.missing",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l3",
                        "missing": missing,
                        "after_ask": True,
                    },
                )
                return {**self.fallback.needs_input(missing), "session_id": session.session_id}

        self.fsm.transition(session, "info_ready")
        self.logger.info(
            "generate.start",
            extra={
                "trace_id": trace_id,
                "session_id": session.session_id,
                "layer": "l3",
                "sections": len(contract.sections),
            },
        )

        self.sessions.set_drafts(session, self.queue.generate_all(skill, session.collected))
        self.fsm.transition(session, "generate_done")
        self.logger.info(
            "generate.done",
            extra={
                "trace_id": trace_id,
                "session_id": session.session_id,
                "layer": "l3",
                "drafts": len(session.drafts),
            },
        )

        while True:
            draft = DraftDocument(
                title=session.collected.get("title", contract.name),
                sections=[{"heading": h, "body": b} for h, b in session.drafts.items()],
                output=contract.output,
            )
            result = self.gates.run(draft, contract, session, trace_id)
            session.gate_history.append(result)

            self.logger.info(
                "gate.round",
                extra={
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "layer": "l3",
                    "rewrite_rounds": session.rewrite_rounds,
                    "passed": result.passed,
                    "score": result.score,
                },
            )

            if result.passed:
                self.fsm.transition(session, "gate_pass")
                out = None
                if contract.output == "docx" and out_path is not None:
                    safe = self._validate_render_target(Path(out_path))
                    safe.parent.mkdir(parents=True, exist_ok=True)
                    out = self.renderer.render(draft, safe)
                self.logger.info(
                    "run.delivered",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l3",
                        "has_output": out is not None,
                    },
                )
                return {
                    "status": "delivered",
                    "session_id": session.session_id,
                    "skill": contract.name,
                    "draft": draft,
                    "gate": result,
                    "output_path": str(out) if out else None,
                }

            if session.rewrite_rounds >= self.config.settings.max_rewrite_rounds:
                self.fsm.transition(session, "gate_fail_limit")
                self.logger.warning(
                    "run.fallback",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l3",
                        "rewrite_rounds": session.rewrite_rounds,
                        "rules_failed": sorted({f.rule for f in result.failures}),
                    },
                )
                return {**self.fallback.template(session, result), "session_id": session.session_id}

            self.fsm.transition(session, "gate_fail")
            self.logger.info(
                "rewrite.round",
                extra={
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "layer": "l3",
                    "rules_failed": sorted(
                        {f.rule for f in result.failures if f.severity == "error"}
                    ),
                },
            )
            self.sessions.set_drafts(
                session,
                self.rewriter.apply(session.drafts, result, skill, session.collected),
            )
            self.sessions.bump_rewrite(session)
            self.fsm.transition(session, "rewrite_done")

    def run_file(self, skill: str, input_path: str) -> int:
        """CLI 入口：从 JSON 读请求与已采集字段，结果写回同目录。"""
        payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
        raw_out = payload.get("out_path") or "output.docx"
        trace_id = uuid.uuid4().hex
        result = self.run(
            request=payload.get("request", skill),
            collected=payload.get("collected", {}),
            out_path=Path(raw_out),
            trace_id=trace_id,
        )
        print(
            json.dumps(
                {k: v for k, v in result.items() if k != "draft"},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if result["status"] == "delivered" else 1

    def _output_root(self) -> Path | None:
        raw = self.config.settings.output_dir or os.getenv("SKILLFORGE_OUTPUT_DIR")
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_absolute() else self.config.root / p

    def _validate_render_target(self, out_path: Path) -> Path:
        if out_path.suffix.lower() != ".docx":
            raise RenderError("输出路径必须以 .docx 结尾")
        root = self._output_root()
        if root is None:
            return out_path
        resolved = out_path.resolve() if out_path.is_absolute() else (root / out_path).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise RenderError("输出路径越过允许目录") from exc
        return resolved
