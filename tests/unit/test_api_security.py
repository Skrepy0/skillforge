"""FastAPI 接入的安全加固测试：鉴权、限流、out_path 白名单。"""

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


def _fake_orchestrator(monkeypatch):
    """用固定结果替换 Orchestrator，避免真实生成。"""

    class _FakeOrch:
        def run(self, **kwargs):
            return {
                "status": "delivered",
                "session_id": "s1",
                "skill": "test-skill",
                "gate": None,
                "missing": None,
                "message": None,
                "output_path": None,
            }

    from skillforge.l3_orchestration.orchestrator import Orchestrator

    monkeypatch.setattr(
        Orchestrator,
        "from_config",
        classmethod(lambda cls, llm=None: _FakeOrch()),
    )


def _client(**kwargs) -> TestClient:
    kwargs.setdefault("llm", _StubLLM())
    return TestClient(api.create_app(**kwargs))


# ---------- 鉴权 ----------


def test_missing_key_returns_401(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=0)
    resp = client.post("/generate", json={"request": "hi"})
    assert resp.status_code == 401
    assert API_KEY not in resp.text


def test_wrong_key_returns_401(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=0)
    resp = client.post(
        "/generate",
        json={"request": "hi"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
    assert API_KEY not in resp.text


def test_correct_key_passes_auth(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=0)
    resp = client.post(
        "/generate",
        json={"request": "hi"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"


def test_healthz_no_auth_required():
    client = _client(api_key=API_KEY, rate_limit_per_minute=0)
    assert client.get("/healthz").status_code == 200


def test_no_llm_and_no_key_returns_503():
    client = TestClient(api.create_app(llm=None, api_key=None, rate_limit_per_minute=0))
    assert client.post("/generate", json={"request": "hi"}).status_code == 503


def test_no_key_but_llm_returns_401(monkeypatch):
    # 只缺 key：认证应拒绝，而不是静默放行
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=None, rate_limit_per_minute=0)
    resp = client.post("/generate", json={"request": "hi"}, headers={"X-API-Key": "anything"})
    assert resp.status_code == 401


# ---------- 限流 ----------


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=1)
    headers = {"X-API-Key": API_KEY}

    first = client.post("/generate", json={"request": "hi"}, headers=headers)
    assert first.status_code == 200

    second = client.post("/generate", json={"request": "hi"}, headers=headers)
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    assert int(second.headers["Retry-After"]) >= 1
    assert API_KEY not in second.text


def test_rate_limit_zero_disables(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=0)
    headers = {"X-API-Key": API_KEY}
    for _ in range(5):
        assert client.post("/generate", json={"request": "hi"}, headers=headers).status_code == 200


def test_rate_limit_independent_per_key(monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(api_key=API_KEY, rate_limit_per_minute=1)

    assert (
        client.post("/generate", json={"request": "hi"}, headers={"X-API-Key": API_KEY}).status_code
        == 200
    )
    assert (
        client.post("/generate", json={"request": "hi"}, headers={"X-API-Key": API_KEY}).status_code
        == 429
    )
    # 换一个 key 的请求用不同 bucket，不会被前一个 key 的配额影响
    # （这个 key 认证会 401，但限流 bucket 是独立的，不会返回 429）
    other = client.post("/generate", json={"request": "hi"}, headers={"X-API-Key": "another-key"})
    assert other.status_code == 401


# ---------- out_path 白名单 ----------


def test_out_path_rejected_when_output_dir_not_configured(monkeypatch):
    _fake_orchestrator(monkeypatch)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)

    app = api.create_app(
        llm=_StubLLM(),
        api_key=API_KEY,
        rate_limit_per_minute=0,
    )

    client = TestClient(app)
    resp = client.post(
        "/generate",
        json={"request": "hi", "out_path": "out.docx"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.docx",
        "sub/../../escape.docx",
        "/abs/path.docx",
        "notes.txt",
        "no-extension",
        "",
    ],
)
def test_out_path_invalid_rejected(tmp_path: Path, monkeypatch, bad_path):
    _fake_orchestrator(monkeypatch)
    client = _client(
        api_key=API_KEY,
        rate_limit_per_minute=0,
        allowed_output_dir=tmp_path,
    )
    resp = client.post(
        "/generate",
        json={"request": "hi", "out_path": bad_path},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400, bad_path


def test_out_path_allowed_relative_docx(tmp_path: Path, monkeypatch):
    _fake_orchestrator(monkeypatch)
    client = _client(
        api_key=API_KEY,
        rate_limit_per_minute=0,
        allowed_output_dir=tmp_path,
    )
    resp = client.post(
        "/generate",
        json={"request": "hi", "out_path": "sub/out.docx"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    # 响应只回显相对路径，不泄露服务端绝对路径
    body = resp.json()
    assert body["output_path"] == "sub/out.docx"
    assert str(tmp_path) not in resp.text
