"""主协调器：把路由、会话、生成、门禁、重写、渲染串成完整流程。"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from skillforge.l1_governance.gate_runner import GateRunner
from skillforge.l2_capability.loader import Loader
from skillforge.l2_capability.pptx_content import normalize_slide_content
from skillforge.l2_capability.renderer.docx_renderer import DocxRenderer
from skillforge.l2_capability.renderer.markdown_renderer import MarkdownRenderer, markdown_text
from skillforge.l2_capability.renderer.pptx_renderer import PptxRenderer
from skillforge.l2_capability.sanitize import filter_collected
from skillforge.l3_orchestration.contract import missing_fields
from skillforge.l3_orchestration.fallback import Fallback
from skillforge.l3_orchestration.rewrite import Rewriter
from skillforge.l3_orchestration.router import Router
from skillforge.l3_orchestration.session import SessionManager
from skillforge.l3_orchestration.session_store import SessionStore
from skillforge.l3_orchestration.state_machine import StateMachine
from skillforge.l3_orchestration.task_queue import LLMClient, TaskQueue
from skillforge.shared.config import AppConfig, load_config
from skillforge.shared.errors import RenderError
from skillforge.shared.logger import get_logger
from skillforge.shared.paths import PathValidationError, resolve_output_path
from skillforge.shared.types import DraftDocument, RouteDecision, SessionPhase, SkillContract


class _MissingLLM:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError("未注入 LLMClient：请在 Orchestrator.from_config(llm=...) 传入")


class RendererProtocol(Protocol):
    """渲染器契约：把 DraftDocument 落盘为指定格式，返回输出路径。

    DocxRenderer 和 PptxRenderer 在结构上满足此协议，不需要显式继承。
    测试里的 spy 只要实现 render() 就能直接替换，不需要继承真实类。
    """

    def render(self, draft: DraftDocument, out_path: Path) -> Path: ...


class Orchestrator:
    def __init__(
        self, config: AppConfig, llm: LLMClient, session_store: SessionStore | None = None
    ) -> None:
        self.config = config
        self.logger = get_logger("skillforge.l3", config.logging)
        self.loader = Loader(config.skills_root)
        self.router = Router(config.routing)
        self.sessions = SessionManager(session_store)
        self.fsm = StateMachine()
        self.queue = TaskQueue(llm, config.settings.queue_concurrency)
        self.rewriter = Rewriter(llm)
        self.gates = GateRunner(config.gates)
        self.renderer: RendererProtocol = DocxRenderer()
        self.pptx_renderer: PptxRenderer = PptxRenderer()
        self.fallback = Fallback()

    @classmethod
    def from_config(
        cls, llm: LLMClient | None = None, session_store: SessionStore | None = None
    ) -> Orchestrator:
        return cls(load_config(), llm or _MissingLLM(), session_store)

    def run(
        self,
        request: str = "",
        collected: dict[str, str] | None = None,
        ask_fn: Callable[[list[str]], dict[str, str]] | None = None,
        out_path: Path | None = None,
        trace_id: str = "",
        session_id: str | None = None,
        pptx_agent: bool = False,
        pptx_assets: dict[str, Path] | None = None,
        pptx_preview: bool = False,
        skill_name: str | None = None,
    ) -> dict:
        if not trace_id:
            trace_id = uuid.uuid4().hex

        stored = self.sessions.store.get(session_id) if session_id else None
        decision = (
            RouteDecision(skill=skill_name, confidence=1.0)
            if skill_name
            else RouteDecision(skill=stored.skill, confidence=1.0)
            if stored is not None and not request.strip()
            else self.router.route(request)
        )
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

        session = self.sessions.get_or_create(decision.skill, session_id)
        if session.phase != SessionPhase.COLLECTING:
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

        if isinstance(self.queue.llm, _MissingLLM):
            raise NotImplementedError(
                "未注入 LLMClient：请在 Orchestrator.from_config(llm=...) 传入"
            )
        self.fsm.transition(session, "info_ready")
        if pptx_agent:
            from skillforge.l3_orchestration.pptx_agent import PptxAgent

            if contract.output != "pptx" or out_path is None:
                raise RenderError("PPT 编辑代理需要 output=pptx 的技能和输出路径")
            template = self._resolve_template(skill, contract)
            if template is None:
                raise RenderError("PPT 编辑代理需要技能配置 template")
            safe = self._validate_render_target(Path(out_path), ".pptx")
            edit_result = PptxAgent(self.queue.llm, preview=pptx_preview).run(
                template,
                safe,
                {
                    "request": request,
                    "collected": session.collected,
                    "sections": contract.sections,
                    "page_plan": contract.pptx_page_plan,
                    "reference_data": {
                        "instructions": skill.instructions,
                        "references": skill.references,
                    },
                },
                assets=pptx_assets,
            )
            event = "edit_complete" if edit_result["status"] == "delivered" else "edit_incomplete"
            self.fsm.transition(session, event)
            self.sessions.store.save(session)
            return {**edit_result, "session_id": session.session_id, "skill": contract.name}
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
                title=session.collected.get("title")
                or session.collected.get("topic_title", contract.name),
                sections=[
                    {
                        "heading": h,
                        "body": normalize_slide_content(b, h, session.collected)
                        if contract.output == "pptx"
                        else b,
                    }
                    for h, b in session.drafts.items()
                ],
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
                if out_path is not None:
                    expected = ".md" if contract.output == "markdown" else f".{contract.output}"
                    safe = self._validate_render_target(Path(out_path), expected)
                    safe.parent.mkdir(parents=True, exist_ok=True)

                    if contract.output == "markdown":
                        out = MarkdownRenderer().render(draft, safe)
                    elif contract.output == "docx":
                        out = self.renderer.render(draft, safe)
                    else:
                        template = self._resolve_template(skill, contract)
                        out = self.pptx_renderer.render(
                            draft,
                            safe,
                            template=template,
                            layouts=contract.pptx_layouts,
                        )
                self.logger.info(
                    "run.delivered",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l3",
                        "has_output": out is not None,
                    },
                )
                self.sessions.store.save(session)
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
                self.sessions.store.save(session)
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
        """CLI 入口：从 JSON 读请求与已采集字段，结果写回同目录。

        默认输出文件名按技能契约的 output 决定：
        - docx → output.docx
        - pptx → output.pptx
        - markdown → 不落盘，只返回草稿
        """
        payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))

        contract = self.loader.load_contract(skill)
        raw_out = payload.get("out_path")
        if raw_out:
            out_path: Path | None = Path(raw_out)
        elif contract.output in ("docx", "pptx"):
            out_path = Path(f"output.{contract.output}")
        else:
            out_path = None  # markdown 不落盘

        trace_id = uuid.uuid4().hex
        result = self.run(
            request=payload.get("request", skill),
            collected=payload.get("collected", {}),
            out_path=out_path,
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
        if result.get("draft") is not None and result["draft"].output == "markdown":
            print(markdown_text(result["draft"]))
        return 0 if result["status"] == "delivered" else 1

    def _output_root(self) -> Path | None:
        raw = self.config.settings.output_dir or os.getenv("SKILLFORGE_OUTPUT_DIR")
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_absolute() else self.config.root / p

    def _validate_render_target(self, out_path: Path, expected_suffix: str = ".docx") -> Path:
        try:
            resolved = resolve_output_path(
                out_path,
                allowed_root=self._output_root(),
                require_root=False,
                expected_suffix=expected_suffix,
                allow_absolute=True,
            )
        except PathValidationError as exc:
            raise RenderError(str(exc)) from exc
        assert resolved is not None
        return resolved

    def _resolve_template(self, skill, contract: SkillContract) -> Path | None:
        if not contract.template:
            return None
        # skill.instructions 不含路径，用 loader 的 skills_root 拼
        base = self.loader.skills_root / "subskills" / contract.name
        candidate = (base / contract.template).resolve()
        root = self.loader.skills_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise RenderError("模板路径越过技能包目录") from exc
        if not candidate.exists():
            raise RenderError(f"模板文件不存在: {contract.template}")
        return candidate
