import json

import httpx
import pytest

from local_doc_chat.agent.model import ModelError, OllamaChatModel


def model_with(handler: httpx.MockTransport) -> OllamaChatModel:
    client = httpx.Client(transport=handler, base_url="http://ollama.test")
    return OllamaChatModel("test-model", client=client)


def test_sends_prompt_and_returns_reply() -> None:
    seen: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi there"}})

    reply = model_with(httpx.MockTransport(handle)).complete("hello")

    assert reply == "hi there"
    assert seen[0]["model"] == "test-model"
    assert seen[0]["stream"] is False
    assert seen[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen[0]["options"] == {"temperature": 0}


def test_missing_model_says_how_to_pull_it() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "nope"}))

    with pytest.raises(ModelError, match="ollama pull test-model"):
        model_with(transport).complete("x")


def test_server_error_is_wrapped() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="boom"))

    with pytest.raises(ModelError, match="500"):
        model_with(transport).complete("x")


def test_unreachable_server_is_wrapped() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelError, match="reach Ollama"):
        model_with(httpx.MockTransport(refuse)).complete("x")


def test_unexpected_shape_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"nope": 1}))

    with pytest.raises(ModelError, match="unreadable"):
        model_with(transport).complete("x")
