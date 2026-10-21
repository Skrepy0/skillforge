"""分章生成：逐章组装 prompt 并调用 LLMClient，控制并发。

LLMClient 是必需协议，只要求 complete()。
SystemPromptLLMClient 是可选协议，实现者额外提供 complete_system()，
可获得 system/user 分离的调用方式；未实现时回退到拼接。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, runtime_checkable

from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.prompt_builder import (
    build_system_prompt,
    build_user_prompt,
)


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
        system = build_system_prompt()
        user = build_user_prompt(skill, section, collected)
        if isinstance(self.llm, SystemPromptLLMClient):
            return self.llm.complete_system(system, user).strip()
        return self.llm.complete(system + "\n\n" + user).strip()

    def generate_all(self, skill: LoadedSkill, collected: dict[str, str]) -> dict[str, str]:
        sections = skill.contract.sections

        def _one(section: str) -> tuple[str, str]:
            return section, self._call(section, skill, collected)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            results = list(pool.map(_one, sections))

        return dict(results)
