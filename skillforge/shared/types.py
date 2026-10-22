"""跨层数据契约。只放 dataclass / Enum，不放业务逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class SessionPhase(StrEnum):
    COLLECTING = "collecting"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    REWRITING = "rewriting"
    DELIVERED = "delivered"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RouteDecision:
    skill: str | None
    confidence: float
    candidates: list[tuple[str, float]] = field(default_factory=list)
    needs_clarification: bool = False


@dataclass(frozen=True)
class SkillContract:
    name: str
    description: str
    required_fields: list[str]
    output: Literal["markdown", "docx", "pptx"]
    sections: list[str]
    gates: dict[str, float] = field(default_factory=dict)
    version: str = "0.1.0"


@dataclass(frozen=True)
class GateFailure:
    rule: str
    section: str
    evidence: str
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True)
class GateResult:
    passed: bool
    score: float
    threshold: float
    failures: list[GateFailure] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    skill: str
    phase: SessionPhase = SessionPhase.COLLECTING
    collected: dict[str, str] = field(default_factory=dict)
    drafts: dict[str, str] = field(default_factory=dict)
    rewrite_rounds: int = 0
    gate_history: list[GateResult] = field(default_factory=list)


@dataclass(frozen=True)
class DraftDocument:
    title: str
    sections: list[dict[str, str]]
    output: Literal["markdown", "docx", "pptx"] = "markdown"
