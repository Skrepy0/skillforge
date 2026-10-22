"""输出路径校验：白名单目录、后缀、逃逸防护。

- API 模式：require_root=True，未配置 allowed_root 时拒绝（调用方转 403）。
- CLI 模式：require_root=False，允许任意路径，但保留 .. 逃逸与后缀校验。
- 所有错误消息统一为“非法输出路径”，不泄露服务端路径。
"""

from __future__ import annotations

from pathlib import Path

MAX_PATH_DEPTH = 3
_ALLOWED_SUFFIXES = (".docx", ".pptx")
_SAFE_MESSAGE = "非法输出路径"


class PathValidationError(ValueError):
    """路径校验失败；message 可直接返回给客户端。"""


def _has_control_chars(text: str) -> bool:
    return any(ord(c) < 32 for c in text) or "\x7f" in text


def resolve_output_path(
    raw: Path | str | None,
    allowed_root: Path | None,
    *,
    require_root: bool = False,
    max_depth: int = MAX_PATH_DEPTH,
) -> Path | None:
    if raw is None:
        return None

    text = str(raw).strip()
    if not text or _has_control_chars(text):
        raise PathValidationError(_SAFE_MESSAGE)

    p = Path(text)
    if p.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise PathValidationError(_SAFE_MESSAGE)
    if any(part == ".." for part in p.parts):
        raise PathValidationError(_SAFE_MESSAGE)

    if allowed_root is None:
        if require_root:
            raise PathValidationError("服务端未启用文件输出")
        return p

    if p.is_absolute() or text.startswith(("/", "\\")):
        raise PathValidationError(_SAFE_MESSAGE)

    depth = len([part for part in p.parts if part not in (".", "")])
    if depth > max_depth:
        raise PathValidationError(_SAFE_MESSAGE)

    root = allowed_root.resolve()
    try:
        resolved = (root / p).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathValidationError(_SAFE_MESSAGE) from exc
    return resolved


def ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathValidationError("无法创建输出目录") from exc
