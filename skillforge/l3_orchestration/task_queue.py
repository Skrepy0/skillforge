"""分章生成：逐章组装 prompt 并调用 LLMClient，控制并发。

LLMClient 是必需协议，只要求 complete()。
SystemPromptLLMClient 是可选协议，实现者额外提供 complete_system()，
可获得 system/user 分离的调用方式；未实现时回退到拼接。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, runtime_checkable

from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.pptx_content import (
    fit_slide_content,
    slide_content_errors,
    supplied_slide_content,
)
from skillforge.l2_capability.prompt_builder import (
    build_slide_repair_prompt,
    build_system_prompt,
    build_user_prompt,
)
from skillforge.shared.errors import LLMError, SkillForgeError


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


@runtime_checkable
class SystemPromptLLMClient(Protocol):
    def complete_system(self, system: str, user: str) -> str: ...


class TaskQueue:
    def __init__(self, llm: LLMClient, concurrency: int = 3) -> None:
        self.llm = llm
        self.concurrency = max(1, concurrency)

    def _call(self, section: str, skill: LoadedSkill, collected: dict[str, str]) -> str:
        plan = skill.contract.pptx_page_plan.get(section, {})
        supplied = (
            supplied_slide_content(section, collected, plan)
            if skill.contract.output == "pptx"
            else None
        )
        if supplied is not None:
            content = supplied
            errors = slide_content_errors(content, section, collected, plan)
            if errors:
                raise LLMError(f"页面“{section}”的采集资料不符合单页预算：" + "；".join(errors))
            return content
        system = build_system_prompt()
        user = build_user_prompt(skill, section, collected)
        original_user = user
        try:
            for _ in range(3):
                if isinstance(self.llm, SystemPromptLLMClient):
                    content = self.llm.complete_system(system, user).strip()
                else:
                    content = self.llm.complete(system + "\n\n" + user).strip()
                if skill.contract.output == "pptx":
                    content = fit_slide_content(content, section, collected, plan)
                errors = (
                    slide_content_errors(content, section, collected, plan)
                    if skill.contract.output == "pptx"
                    else []
                )
                if not errors:
                    return content
                user = original_user + build_slide_repair_prompt(content, errors)
            raise LLMError(f"章节“{section}”连续3次未满足单页预算：{'；'.join(errors)}")
        except SkillForgeError:
            raise
        except Exception as exc:
            raise LLMError("章节 LLM 调用失败") from exc

    def generate_all(self, skill: LoadedSkill, collected: dict[str, str]) -> dict[str, str]:
        sections = skill.contract.sections

        def _one(section: str) -> tuple[str, str]:
            return section, self._call(section, skill, collected)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            results = list(pool.map(_one, sections))

        return dict(results)
