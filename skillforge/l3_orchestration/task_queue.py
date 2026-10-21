"""分章生成：逐章组装 prompt 并调用 LLMClient，控制并发。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.prompt_builder import build_section_prompt


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class TaskQueue:
    def __init__(self, llm: LLMClient, concurrency: int = 3) -> None:
        self.llm = llm
        self.concurrency = max(1, concurrency)

    def generate_all(self, skill: LoadedSkill, collected: dict[str, str]) -> dict[str, str]:
        sections = skill.contract.sections

        def _one(section: str) -> tuple[str, str]:
            prompt = build_section_prompt(skill, section, collected)
            return section, self.llm.complete(prompt).strip()

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            results = list(pool.map(_one, sections))

        return dict(results)
