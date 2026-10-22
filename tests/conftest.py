"""测试全局 fixture。"""

from __future__ import annotations

import pytest
from skillforge.shared.types import (
    DraftDocument,
    GateResult,
    SessionState,
    SkillContract,
)


@pytest.fixture
def sample_contract() -> SkillContract:
    return SkillContract(
        name="sample-skill",
        description="test",
        required_fields=["topic"],
        output="markdown",
        sections=["概述", "正文"],
    )


@pytest.fixture
def sample_session() -> SessionState:
    return SessionState("s1", "sample-skill")


@pytest.fixture
def sample_draft() -> DraftDocument:
    return DraftDocument(
        "标题",
        [
            {"heading": "概述", "body": "概述内容。"},
            {"heading": "正文", "body": "正文内容。"},
        ],
    )


@pytest.fixture
def pass_gate() -> GateResult:
    return GateResult(passed=True, score=1.0, threshold=0.8)


@pytest.fixture
def stub_llm():
    from tests.unit._stubs import StubLLM

    return StubLLM()


@pytest.fixture(autouse=True)
def _isolate_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
