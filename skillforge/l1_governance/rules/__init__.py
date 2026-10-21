"""规则注册表：规则名 → check 函数。

新增规则时：
1. 在 rules/ 下新建模块，实现 check()。
2. 在 RULES 中登记。
3. 在 config/gates.yaml 中注册 enabled 与 weight。
"""

from collections.abc import Callable
from typing import Any

from skillforge.l1_governance.rules import (
    cliche_check,
    format_check,
    placeholder_check,
    repetition_check,
    sensitive_check,
)
from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

RuleFn = Callable[
    [DraftDocument, SkillContract, SessionState, dict[str, Any]],
    list[GateFailure],
]

RULES: dict[str, RuleFn] = {
    "cliche_check": cliche_check.check,
    "format_check": format_check.check,
    "repetition_check": repetition_check.check,
    "sensitive_check": sensitive_check.check,
    "placeholder_check": placeholder_check.check,
}

__all__ = ["RULES"]
