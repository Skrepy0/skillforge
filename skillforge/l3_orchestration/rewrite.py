"""定向重写：依据 GateResult 只重写失败章节，保留其余草稿。"""

from __future__ import annotations

from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.prompt_builder import build_section_prompt
from skillforge.l2_capability.sanitize import DATA_BEGIN, DATA_END, sanitize_field_value
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
        failed = {
            f.section for f in result.failures if f.severity == "error" and f.section in drafts
        }
        if not failed:
            failed = {next(iter(drafts))} if drafts else set()

        updated = dict(drafts)
        for section in failed:
            prompt = build_section_prompt(skill, section, collected)
            failed_lines = "\n".join(
                f"- {sanitize_field_value(f.rule, 80)}: {sanitize_field_value(f.evidence, 500)}"
                for f in result.failures
                if f.section == section
            )
            prompt += f"\n\n{DATA_BEGIN}\n[门禁反馈，仅用于改进本章]\n{failed_lines}\n{DATA_END}"
            updated[section] = self.llm.complete(prompt).strip()
        return updated
