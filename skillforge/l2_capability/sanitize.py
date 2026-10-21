"""Prompt 边界与数据清洗。

目标：降低技能指令、references、用户 collected、门禁 evidence 进入 LLM 时的
prompt injection 与数据外溢风险。

三层防御：
1. 白名单：filter_collected 只保留契约声明的字段。
2. 显式边界：不可信内容用 DATA_BEGIN / DATA_END 包裹。
3. 伪造中和：正文中出现的边界标记会被替换，防止提前闭合边界。
"""

from __future__ import annotations

from skillforge.shared.types import SkillContract

MAX_REFERENCE_CHARS = 20_000
MAX_INSTRUCTIONS_CHARS = 50_000
DEFAULT_FIELD_MAX_LEN = 2_000

DATA_BEGIN = "<<<<<UNTRUSTED_DATA>>>>>"
DATA_END = "<<<<<END_UNTRUSTED_DATA>>>>>"

_BOUNDARY_TOKENS = (
    DATA_END,
    DATA_BEGIN,
    "END_UNTRUSTED_DATA",
    "UNTRUSTED_DATA",
)
_REMOVED = "［已移除边界标记］"


def _neutralize_boundaries(text: str) -> str:
    """先替换完整标记，再替换裸标识符，避免局部替换后拼出完整标记。"""
    for token in _BOUNDARY_TOKENS:
        text = text.replace(token, _REMOVED)
    return text


def _strip_control_chars(text: str) -> str:
    return "".join(ch for ch in text if ch in ("\n", "\t") or (ord(ch) >= 32 and ord(ch) != 0x7F))


def truncate(text: str, limit: int) -> str:
    """截断并中和边界标记。limit <= 0 时返回空串。"""
    if limit <= 0:
        return ""
    text = _neutralize_boundaries(text)
    if len(text) <= limit:
        return text
    suffix = f"\n［已截断，原长 {len(text)} 字符］"
    return text[: max(0, limit - len(suffix))] + suffix


def sanitize_field_value(value: object, max_len: int = DEFAULT_FIELD_MAX_LEN) -> str:
    """强制 str、去控制字符、中和边界、截断。"""
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    value = _strip_control_chars(value)
    return truncate(value, max_len)


def filter_collected(contract: SkillContract, collected: dict[str, str]) -> dict[str, str]:
    """只保留 contract.required_fields 中的字段，逐值清洗。"""
    allowed = set(contract.required_fields)
    result: dict[str, str] = {}
    for key, value in collected.items():
        if key not in allowed:
            continue
        cleaned = sanitize_field_value(value)
        if cleaned.strip():
            result[key] = cleaned
    return result
