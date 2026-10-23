from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from skillforge.l3_orchestration.task_queue import SystemPromptLLMClient
from skillforge.l4_interface.llm_client import OpenAICompatibleClient
from skillforge.shared.errors import LLMError, SkillForgeError

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
    client = OpenAICompatibleClient(api_key="secret-key", backoff_base=0.25, json_mode=True)
    sleep = Mock()
    monkeypatch.setattr("skillforge.l4_interface.llm_client.time.sleep", sleep)
    yield client, sleep
    client._client.close()


def response(content="ok", empty=False):
    return SimpleNamespace(
        choices=[] if empty else [SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_visual_uses_rendered_png_content(client, monkeypatch, tmp_path):
    from PIL import Image

    llm, _ = client
    image = tmp_path / "page.png"
    Image.new("RGB", (20, 20), "white").save(image)
    create = Mock(return_value=response('{"done":true}'))
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    assert llm.complete_visual("system", "inspect", [image]) == '{"done":true}'
    message = create.call_args.kwargs["messages"][1]
    assert message["content"][0] == {"type": "text", "text": "inspect"}
    assert message["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}


def test_json_completion_requests_json_mode(client, monkeypatch):
    llm, _ = client
    create = Mock(return_value=response('{"operations":[]}'))
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    assert llm.complete_json("system", "user") == '{"operations":[]}'
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}


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
@pytest.mark.parametrize("system", [False, True])
def test_empty_content(client, monkeypatch, result, system):
    llm, sleep = client
    monkeypatch.setattr(llm._client.chat.completions, "create", Mock(return_value=result))
    with pytest.raises(SkillForgeError, match="模型返回空内容"):
        if system:
            llm.complete_system("system", "prompt")
        else:
            llm.complete("prompt")
    sleep.assert_not_called()


@pytest.mark.parametrize("system", [False, True])
def test_messages_and_result(client, monkeypatch, system):
    llm, _ = client
    create = Mock(return_value=response(" content "))
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    assert isinstance(llm, SystemPromptLLMClient)
    if system:
        assert llm.complete_system("rules", "prompt") == " content "
        messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "prompt"}]
    else:
        assert llm.complete("prompt") == " content "
        messages = [{"role": "user", "content": "prompt"}]
    create.assert_called_once_with(model=llm.model, messages=messages, temperature=0.3)


def test_system_retry(client, monkeypatch):
    llm, sleep = client
    create = Mock(side_effect=[error("timeout"), response()])
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    assert llm.complete_system("rules", "prompt") == "ok"
    assert create.call_count == 2
    assert create.call_args_list[0] == create.call_args_list[1]
    sleep.assert_called_once_with(0.25)
