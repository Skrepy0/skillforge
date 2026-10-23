from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from skillforge.l4_interface.llm_client import OpenAICompatibleClient
from skillforge.shared.errors import LLMError

openai = pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")


def error(kind):
    request = httpx.Request("POST", "https://example.test")
    if kind == "timeout":
        return openai.APITimeoutError(request=request)
    if kind == "connection":
        return openai.APIConnectionError(request=request)
    if kind == "api":
        return openai.APIError("secret-key", request, body=None)
    status = int(kind)
    return openai.APIStatusError(
        "secret-key", response=httpx.Response(status, request=request), body=None
    )


@pytest.fixture
def client(monkeypatch):
    client = OpenAICompatibleClient(api_key="secret-key", backoff_base=0.25)
    sleep = Mock()
    monkeypatch.setattr("skillforge.l4_interface.llm_client.time.sleep", sleep)
    yield client, sleep
    client._client.close()


def response(content="ok", empty=False):
    return SimpleNamespace(
        choices=[] if empty else [SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.parametrize("kind", ["timeout", "connection", "429", "500", "503"])
def test_retry_success(client, monkeypatch, kind):
    llm, sleep = client
    create = Mock(side_effect=[error(kind), error(kind), response()])
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    assert llm.complete("prompt") == "ok"
    assert create.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [0.25, 0.5]
    assert llm._client.max_retries == 0


@pytest.mark.parametrize("kind", ["timeout", "429", "503"])
def test_retry_exhausted(client, monkeypatch, kind):
    llm, sleep = client
    exc = error(kind)
    create = Mock(side_effect=exc)
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    with pytest.raises(LLMError) as caught:
        llm.complete("prompt")
    assert caught.value.__cause__ is exc
    assert "secret-key" not in str(caught.value)
    assert create.call_count == 4
    assert sleep.call_count == 3


@pytest.mark.parametrize("kind", ["400", "401", "403", "404", "api"])
def test_no_retry(client, monkeypatch, kind):
    llm, sleep = client
    exc = error(kind)
    create = Mock(side_effect=exc)
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    with pytest.raises(LLMError) as caught:
        llm.complete("prompt")
    assert caught.value.__cause__ is exc
    assert "secret-key" not in str(caught.value)
    assert create.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "result", [response(None), response(""), response("  "), response(empty=True)]
)
def test_empty_content(client, monkeypatch, result):
    llm, sleep = client
    monkeypatch.setattr(llm._client.chat.completions, "create", Mock(return_value=result))
    with pytest.raises(LLMError, match="空内容"):
        llm.complete("prompt")
    sleep.assert_not_called()
