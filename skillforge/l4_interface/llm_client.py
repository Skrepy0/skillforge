"""LLMClient 实现：OpenAI 兼容接口，支持自定义 base_url。"""

from __future__ import annotations

import os

from skillforge.shared.errors import SkillForgeError


class OpenAICompatibleClient:
    """实现 L3 的 LLMClient 协议：complete(prompt) -> str。"""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SkillForgeError(
                "缺少 openai 依赖：请执行 uv sync --extra api（或 pip install 'skillforge[api]'）"
            ) from exc

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise SkillForgeError(
                "未设置 OPENAI_API_KEY。请在 .env 或环境变量中配置，或改用其它 LLMClient 实现。"
            )

        self.model: str = model or os.getenv("SKILLFORGE_MODEL") or "gpt-4o-mini"
        self._client: OpenAI = OpenAI(
            api_key=key,
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            timeout=timeout,
        )

    def complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = resp.choices[0].message.content
        if not content:
            raise SkillForgeError("模型返回空内容")
        return content
