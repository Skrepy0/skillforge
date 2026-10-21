"""out_path 白名单：403 / 400 / 放行 / 不泄露绝对路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from skillforge.l4_interface import api  # noqa: E402

API_KEY = "test-secret-key"


class _StubLLM:
    def complete(self, prompt: str) -> str:
        return "stub"


def _fake_orchestrator(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    class _FakeOrch:
        def run(self, **kwargs):
            calls.append(kwargs)
            return {
                "status": "delivered",
                "session_id": "s1",
                "skill": "test-skill",
                "gate": None,
                "missing": None,
                "message": None,
                "output_path": kwargs.get("out_path"),
            }

    from skillforge.l3_orchestration.orchestrator import Orchestrator

    monkeypatch.setattr(
        Orchestrator,
        "from_config",
        classmethod(lambda cls, llm=None: _FakeOrch()),
    )
    return calls


def _client(**kwargs) -> TestClient:
    kwargs.setdefault("llm", _StubLLM())
    kwargs.setdefault("api_key", API_KEY)
    kwargs.setdefault("rate_limit_per_minute", 0)
    return TestClient(api.create_app(**kwargs))


def _post(client: TestClient, out_path: str | None):
    body: dict = {"request": "hi"}
    if out_path is not None:
        body["out_path"] = out_path
    return client.post("/generate", json=body, headers={"X-API-Key": API_KEY})


# ---------- 未配置输出目录 ----------


def test_out_path_rejected_when_no_output_dir(monkeypatch):
    _fake_orchestrator(monkeypatch)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)
    client = _client()
    resp = _post(client, "report.docx")
    assert resp.status_code == 403
    assert "未启用文件输出" in resp.json()["detail"]


def test_no_out_path_still_works_without_output_dir(monkeypatch):
    _fake_orchestrator(monkeypatch)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)
    client = _client()
    assert _post(client, None).status_code == 200


# ---------- 非法路径 ----------


@pytest.mark.parametrize(
    "bad",
    [
        "../escape.docx",
        "sub/../../escape.docx",
        "/abs/path.docx",
        "notes.txt",
        "no-extension",
        "",
        "a/b/c/d.docx",  # 超过深度 3
        "bad\x00name.docx",  # NUL
    ],
)
def test_invalid_out_path_returns_400(tmp_path: Path, monkeypatch, bad: str):
    _fake_orchestrator(monkeypatch)
    client = _client(allowed_output_dir=tmp_path)
    resp = _post(client, bad)
    assert resp.status_code == 400, bad
    # 不泄露服务端绝对路径
    assert str(tmp_path) not in resp.text


def test_absolute_path_outside_root_rejected(tmp_path: Path, monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(allowed_output_dir=tmp_path)
    outside = str(tmp_path.parent / "escape.docx")
    resp = _post(client, outside)
    assert resp.status_code == 400
    assert str(tmp_path) not in resp.text


# ---------- 放行 ----------


@pytest.mark.parametrize("ok", ["report.docx", "sub/dir/report.docx"])
def test_allowed_relative_docx(tmp_path: Path, monkeypatch, ok: str):
    calls = _fake_orchestrator(monkeypatch)
    client = _client(allowed_output_dir=tmp_path)
    resp = _post(client, ok)
    assert resp.status_code == 200, resp.text

    # 传入 run() 的 out_path 已解析到白名单内
    assert calls, "orchestrator.run 未被调用"
    passed = calls[-1]["out_path"]
    assert isinstance(passed, Path)
    assert passed.suffix == ".docx"
    passed.resolve().relative_to(tmp_path.resolve())  # 不抛即通过

    # 响应只回显相对路径
    body = resp.json()
    assert body["output_path"] == ok
    assert str(tmp_path) not in resp.text


def test_env_var_output_dir_used(tmp_path: Path, monkeypatch):
    _fake_orchestrator(monkeypatch)
    monkeypatch.setenv("SKILLFORGE_OUTPUT_DIR", str(tmp_path))
    client = _client()  # 不传 allowed_output_dir，靠环境变量
    resp = _post(client, "report.docx")
    assert resp.status_code == 200
    assert resp.json()["output_path"] == "report.docx"
    assert str(tmp_path) not in resp.text
