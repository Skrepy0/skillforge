"""主协调器：把路由、会话、生成、门禁、重写、渲染串成完整流程。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from skillforge.l1_governance.gate_runner import GateRunner
from skillforge.l2_capability.loader import Loader
from skillforge.l2_capability.renderer.docx_renderer import DocxRenderer
from skillforge.l3_orchestration.contract import missing_fields
from skillforge.l3_orchestration.fallback import Fallback
from skillforge.l3_orchestration.rewrite import Rewriter
from skillforge.l3_orchestration.router import Router
from skillforge.l3_orchestration.session import SessionManager
from skillforge.l3_orchestration.state_machine import StateMachine
from skillforge.l3_orchestration.task_queue import LLMClient, TaskQueue
from skillforge.shared.config import AppConfig, load_config
from skillforge.shared.types import DraftDocument


class _MissingLLM:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError("未注入 LLMClient：请在 Orchestrator.from_config(llm=...) 传入")


class Orchestrator:
    def __init__(self, config: AppConfig, llm: LLMClient) -> None:
        self.config = config
        self.loader = Loader(config.skills_root)
        self.router = Router(config.routing)
        self.sessions = SessionManager()
        self.fsm = StateMachine()
        self.queue = TaskQueue(llm, config.settings.queue_concurrency)
        self.rewriter = Rewriter(llm)
        self.gates = GateRunner(config.gates)
        self.renderer = DocxRenderer(config.skills_root)
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
        decision = self.router.route(request)
        if decision.needs_clarification or decision.skill is None:
            return self.fallback.clarify(decision)

        skill = self.loader.load(decision.skill)
        contract = skill.contract

        session = self.sessions.create(decision.skill)
        self.sessions.merge(session, collected or {})

        # 阶段一：采集
        missing = missing_fields(contract, session.collected)
        if missing:
            if ask_fn is None:
                return {**self.fallback.needs_input(missing), "session_id": session.session_id}
            self.sessions.merge(session, self.fallback.ask(missing, ask_fn))
            missing = missing_fields(contract, session.collected)
            if missing:
                return {**self.fallback.needs_input(missing), "session_id": session.session_id}

        self.fsm.transition(session, "info_ready")

        # 阶段二：分章生成
        self.sessions.set_drafts(session, self.queue.generate_all(skill, session.collected))
        self.fsm.transition(session, "generate_done")

        # 阶段三：门禁 + 定向重写
        while True:
            draft = DraftDocument(
                title=session.collected.get("title", contract.name),
                sections=[{"heading": h, "body": b} for h, b in session.drafts.items()],
                output=contract.output,
            )
            result = self.gates.run(draft, contract, session, trace_id)
            session.gate_history.append(result)

            if result.passed:
                self.fsm.transition(session, "gate_pass")
                out = None
                if contract.output == "docx" and out_path:
                    out = self.renderer.render(draft, Path(out_path))
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
                return {**self.fallback.template(session, result), "session_id": session.session_id}

            self.fsm.transition(session, "gate_fail")
            self.sessions.set_drafts(
                session,
                self.rewriter.apply(session.drafts, result, skill, session.collected),
            )
            self.sessions.bump_rewrite(session)
            self.fsm.transition(session, "rewrite_done")

    def run_file(self, skill: str, input_path: str) -> int:
        """CLI 入口：从 JSON 读请求与已采集字段，结果写回同目录。"""
        payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
        result = self.run(
            request=payload.get("request", skill),
            collected=payload.get("collected", {}),
            out_path=Path(payload.get("out_path", "output.docx")),
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
