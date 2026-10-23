"""LLMClient 实现：OpenAI 兼容接口，支持自定义 base_url。"""

from __future__ import annotations

import math
import os
import time
from base64 import b64encode
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam

from skillforge.shared.errors import ConfigError, LLMError, SkillForgeError


class OpenAICompatibleClient:
    """实现 L3 的 LLMClient 与 SystemPromptLLMClient，支持 complete 和 complete_system。"""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        json_mode: bool | None = None,
    ) -> None:
        from skillforge.shared.config import load_project_dotenv

        if max_retries < 0 or not math.isfinite(backoff_base) or backoff_base < 0:
            raise ConfigError("max_retries 和 backoff_base 必须非负，退避时间必须有限")
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        load_project_dotenv()
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
        endpoint = base_url or os.getenv("OPENAI_BASE_URL")
        # Compatible providers vary in response_format support. The editor still
        # validates JSON locally when this provider feature is disabled.
        self.json_mode = (
            json_mode
            if json_mode is not None
            else os.getenv("SKILLFORGE_JSON_MODE", "false" if endpoint else "true").lower()
            in {"true", "1", "yes"}
        )
        self._client: OpenAI = OpenAI(
            api_key=key,
            base_url=endpoint,
            timeout=timeout,
            max_retries=0,  # 重试由本层统一控制，避免 SDK 重试叠加。
        )

    def complete(self, prompt: str) -> str:
        return self._create([{"role": "user", "content": prompt}])

    def complete_system(self, system: str, user: str) -> str:
        return self._create(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )

    def complete_json(self, system: str, user: str) -> str:
        return self._create(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=self.json_mode,
        )

    def complete_visual(self, system: str, user: str, images: list[Path]) -> str:
        """Use real rendered PNG pages with a vision-capable compatible model."""
        if not 1 <= len(images) <= 4:
            raise LLMError("每轮视觉检查必须提供1至4张 PNG 预览")
        content: list[ChatCompletionContentPartParam] = [{"type": "text", "text": user}]
        for path in images:
            data = path.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 10 * 1024 * 1024:
                raise LLMError("预览必须是小于10MB的 PNG 文件")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64," + b64encode(data).decode("ascii")
                    },
                }
            )
        return self._create(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            json_mode=self.json_mode,
        )

    def _create(self, messages: list[ChatCompletionMessageParam], json_mode: bool = False) -> str:
        """首次调用失败后最多重试 max_retries 次，按基数指数退避。"""
        from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

        for attempt in range(self.max_retries + 1):
            try:
                options: dict[str, Any] = (
                    {"response_format": {"type": "json_object"}} if json_mode else {}
                )
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    **options,
                )
            except APIError as exc:
                # APITimeoutError 继承 APIConnectionError。
                retryable = isinstance(exc, (APIConnectionError, RateLimitError)) or (
                    isinstance(exc, APIStatusError)
                    and (exc.status_code == 429 or 500 <= exc.status_code < 600)
                )
                if not retryable or attempt == self.max_retries:
                    # 不包含 SDK 错误正文、请求或 URL，避免泄露凭据。
                    raise LLMError("LLM 调用失败：不可重试或重试次数已耗尽") from exc
                time.sleep(self.backoff_base * 2**attempt)
                continue
            content = resp.choices[0].message.content if resp.choices else None
            if not content or not content.strip():
                raise LLMError("模型返回空内容")
            return content
        raise LLMError("LLM 调用失败")  # 防御性保护
