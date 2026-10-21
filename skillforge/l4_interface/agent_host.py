"""Agent 宿主适配：纯函数入口，无 I/O、无阻塞。"""

from __future__ import annotations

from typing import Any

from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.l3_orchestration.task_queue import LLMClient


def handle(
    request: str,
    collected: dict[str, str] | None = None,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """一次调用完成一次生成。缺信息时返回 needs_input，由宿主向用户追问后重调。"""
    orchestrator = Orchestrator.from_config(llm=llm)
    result = orchestrator.run(
        request=request,
        collected=collected or {},
        ask_fn=None,
    )
    # 去掉 DraftDocument，宿主不需要，且不可 JSON 序列化
    return {k: v for k, v in result.items() if k != "draft"}
