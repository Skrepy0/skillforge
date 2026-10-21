"""定向重写：依据 GateResult 只重写失败章节，保留其余草稿。"""

from __future__ import annotations

from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.prompt_builder import build_section_prompt
from skillforge.l3_orchestration.task_queue import LLMClient
from skillforge.shared.types import GateResult


class Rewriter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def apply(
        self,
        drafts: dict[str, str],
        result: GateResult,
        skill: LoadedSkill,
        collected: dict[str, str],
    ) -> dict[str, str]:
        # 只取该技能契约内的章节，避免把“（全文）”这类伪章节当章重写
        failed = {
            f.section for f in result.failures if f.severity == "error" and f.section in drafts
        }
        if not failed:
            # 失败发生在全文级（如字数），退化为整体重写失败最多的章
            failed = {next(iter(drafts))} if drafts else set()

        updated = dict(drafts)
        for section in failed:
            prompt = build_section_prompt(skill, section, collected)
            prompt += "\n\n上一版被门禁打回，原因：\n" + "\n".join(
                f"- {f.rule}: {f.evidence}" for f in result.failures if f.section == section
            )
            updated[section] = self.llm.complete(prompt).strip()
        return updated
