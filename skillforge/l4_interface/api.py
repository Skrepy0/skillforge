"""FastAPI 接入：POST /generate、GET /healthz。

安全加固：
1. X-API-Key 鉴权：密钥来自 create_app 参数或 SKILLFORGE_API_KEY 环境变量。
2. per-key/per-IP 固定窗口限流：rate_limit_per_minute 参数或
   SKILLFORGE_RATE_LIMIT_PER_MINUTE 环境变量；0 表示禁用（仅测试/本地用）。
3. out_path 白名单：allowed_output_dir 参数或 SKILLFORGE_OUTPUT_DIR 环境变量；
   未配置时拒绝任何 out_path。
"""

import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from skillforge.l3_orchestration.task_queue import LLMClient
from skillforge.shared.paths import PathValidationError, ensure_parent, resolve_output_path


class GenerateRequest(BaseModel):
    request: str = Field(..., description="用户原始请求，如“帮我写开题报告”")
    skill: str | None = Field(None, description="可选：直接指定技能，跳过路由")
    collected: dict[str, str] = Field(default_factory=dict)
    out_path: str | None = Field(
        None,
        description=(
            "docx 输出相对路径。仅在服务端通过 SKILLFORGE_OUTPUT_DIR "
            "配置了输出目录时生效；否则请求会被拒绝。"
        ),
    )


class GenerateResponse(BaseModel):
    status: str
    session_id: str | None = None
    skill: str | None = None
    gate: dict[str, Any] | None = None
    failures: list[dict[str, Any]] | None = None
    missing: list[str] | None = None
    output_path: str | None = None
    message: str | None = None


class FixedWindowRateLimiter:
    """per-key 固定窗口内存限流器。线程安全；limit=0 时禁用。"""

    def __init__(self, limit_per_minute: int, window_seconds: float = 60.0) -> None:
        self.limit = max(0, int(limit_per_minute))
        self.window = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def hit(self, key: str) -> tuple[bool, int]:
        """返回 (allowed, retry_after)。allowed=False 时 retry_after >= 1。"""
        if not self.enabled:
            return True, 0

        now = time.monotonic()
        with self._lock:
            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= self.window:
                window_start, count = now, 0
            count += 1
            self._buckets[key] = (window_start, count)
            if count <= self.limit:
                return True, 0
            retry_after = max(1, int(self.window - (now - window_start)))
            return False, retry_after


def _hash_for_bucket(value: str) -> str:
    """不可逆哈希，用于限流 bucket；避免原始 key 进入任何持久结构。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _resolve_out_path(allowed_root: Path, raw: str) -> Path:
    """校验并解析 out_path；非法时抛 ValueError，消息可直接返回给客户端。"""
    candidate = raw.strip()
    if not candidate:
        raise ValueError("out_path 不能为空")

    p = Path(candidate)
    if p.is_absolute() or candidate.startswith(("/", "\\")):
        raise ValueError("out_path 必须是相对路径")
    if any(part == ".." for part in p.parts):
        raise ValueError("out_path 不得包含 '..'")
    if p.suffix.lower() != ".docx":
        raise ValueError("out_path 必须以 .docx 结尾")

    root_resolved = allowed_root.resolve()
    resolved = (root_resolved / p).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("out_path 越过允许的输出目录") from exc
    return resolved


def _parse_rate_limit(value: int | None) -> int:
    if value is not None:
        return max(0, int(value))
    env = os.getenv("SKILLFORGE_RATE_LIMIT_PER_MINUTE")
    if env is None or not env.strip():
        return 30
    try:
        return max(0, int(env))
    except ValueError:
        return 30


def _parse_output_dir(value: Path | str | None) -> Path | None:
    if value is not None:
        return Path(value).resolve()
    env = os.getenv("SKILLFORGE_OUTPUT_DIR")
    if env is None or not env.strip():
        return None
    return Path(env).resolve()


def _gate_dict(gate) -> dict | None:
    if gate is None:
        return None
    return {"passed": gate.passed, "score": gate.score, "threshold": gate.threshold}


def _failures(gate) -> list[dict] | None:
    if gate is None or not gate.failures:
        return None
    return [
        {"rule": f.rule, "section": f.section, "evidence": f.evidence, "severity": f.severity}
        for f in gate.failures
    ]


def create_app(
    llm: LLMClient | None = None,
    api_key: str | None = None,
    rate_limit_per_minute: int | None = None,
    allowed_output_dir: Path | str | None = None,
):
    """创建 FastAPI 应用。

    参数：
        llm: L3 的 LLMClient 实现。为 None 时 /generate 返回 503。
        api_key: 服务端 API 密钥。未传时读取 SKILLFORGE_API_KEY。
        rate_limit_per_minute: 每分钟请求上限。未传时读取
            SKILLFORGE_RATE_LIMIT_PER_MINUTE，再退回 30。0 表示禁用。
        allowed_output_dir: 输出目录白名单。未传时读取
            SKILLFORGE_OUTPUT_DIR。为 None 时拒绝任何 out_path。
    """
    from skillforge.shared.config import load_project_dotenv

    load_project_dotenv()
    from fastapi import Depends, FastAPI, Header, HTTPException, Request

    from skillforge.shared.config import load_config

    try:
        trace_header = load_config().logging.trace_header
    except Exception:
        trace_header = "X-Trace-Id"

    resolved_key = api_key if api_key is not None else os.getenv("SKILLFORGE_API_KEY")
    if resolved_key is not None and not resolved_key.strip():
        resolved_key = None

    limiter = FixedWindowRateLimiter(_parse_rate_limit(rate_limit_per_minute))
    allowed_root = _parse_output_dir(allowed_output_dir)

    app = FastAPI(title="SkillForge", version="0.1.0")
    app.state.limiter = limiter
    app.state.output_root = allowed_root

    async def check_ready() -> None:
        # 两者都缺：服务未就绪。只缺 key：交给 require_api_key 返回 401，
        # 不能因为没配 key 就静默放行。
        if llm is None and not resolved_key:
            raise HTTPException(status_code=503, detail="服务端未配置 LLM 与 API key")

    async def rate_limit(request: Request) -> None:
        raw_key = request.headers.get("X-API-Key")
        if raw_key:
            bucket = "key:" + _hash_for_bucket(raw_key)
        else:
            host = request.client.host if request.client else "unknown"
            bucket = "ip:" + host

        allowed, retry_after = limiter.hit(bucket)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁",
                headers={"Retry-After": str(retry_after)},
            )

    async def require_api_key(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        if not resolved_key:
            raise HTTPException(status_code=401, detail="服务端未配置 API key")
        if not x_api_key or not secrets.compare_digest(x_api_key, resolved_key):
            raise HTTPException(status_code=401, detail="无效的 API key")
        return x_api_key

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/generate",
        response_model=GenerateResponse,
        dependencies=[Depends(check_ready), Depends(rate_limit), Depends(require_api_key)],
    )
    def generate(req: GenerateRequest, request: Request) -> GenerateResponse:
        if llm is None:
            raise HTTPException(status_code=503, detail="LLM 未配置")

        safe_out: Path | None = None
        rel_out: str | None = None

        if req.out_path is not None:
            if allowed_root is None:
                raise HTTPException(status_code=403, detail="服务端未启用文件输出")
            try:
                safe_out = resolve_output_path(
                    req.out_path,
                    allowed_root,
                    require_root=True,
                )
            except PathValidationError as exc:
                raise HTTPException(status_code=400, detail="非法输出路径") from exc
            if safe_out is None:
                # req.out_path 非空时 resolve_output_path 不会返回 None，防御性兜底
                raise HTTPException(status_code=400, detail="非法输出路径")
            ensure_parent(safe_out)
            rel_out = safe_out.relative_to(allowed_root.resolve()).as_posix()

        from skillforge.l3_orchestration.orchestrator import Orchestrator
        from skillforge.shared.errors import SkillNotFound

        try:
            trace_id = request.headers.get(trace_header, "")
            result = Orchestrator.from_config(llm=llm).run(
                request=req.request,
                collected=req.collected,
                ask_fn=None,
                out_path=safe_out,
                trace_id=trace_id,
            )
        except SkillNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return GenerateResponse(
            status=result["status"],
            session_id=result.get("session_id"),
            skill=result.get("skill"),
            gate=_gate_dict(result.get("gate")),
            failures=_failures(result.get("gate")),
            missing=result.get("missing"),
            output_path=rel_out,
            message=result.get("message"),
        )

    return app
