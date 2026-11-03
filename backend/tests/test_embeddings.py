import json

import httpx
import pytest

from local_doc_chat.store.embeddings import EmbeddingError, OllamaEmbedder


def embedder_with(
    handler: httpx.MockTransport | None = None, *, batch_size: int = 32
) -> OllamaEmbedder:
    client = httpx.Client(transport=handler, base_url="http://ollama.test")
    return OllamaEmbedder("test-model", batch_size=batch_size, client=client)


def echo_lengths(requests: list[dict[str, object]]) -> httpx.MockTransport:
    """Answers each input with a 2-d vector [len(text), 0] and records request bodies."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200, json={"embeddings": [[float(len(t)), 0.0] for t in body["input"]]}
        )

    return httpx.MockTransport(handle)


def test_embeds_documents_in_batches_and_keeps_order() -> None:
    requests: list[dict[str, object]] = []
    texts = ["a" * n for n in range(1, 6)]

    vectors = embedder_with(echo_lengths(requests), batch_size=2).embed_documents(texts)

    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert [len(r["input"]) for r in requests] == [2, 2, 1]  # type: ignore[arg-type]
    assert {r["model"] for r in requests} == {"test-model"}


def test_no_texts_makes_no_request() -> None:
    requests: list[dict[str, object]] = []

    assert embedder_with(echo_lengths(requests)).embed_documents([]) == []
    assert requests == []


def test_embed_query_returns_one_vector() -> None:
    assert embedder_with(echo_lengths([])).embed_query("abc") == [3.0, 0.0]


def test_missing_model_says_how_to_pull_it() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(404, json={"error": "model 'test-model' not found"})
    )

    with pytest.raises(EmbeddingError, match="ollama pull test-model"):
        embedder_with(transport).embed_query("x")


def test_server_error_is_wrapped() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="boom"))

    with pytest.raises(EmbeddingError, match="500"):
        embedder_with(transport).embed_query("x")


def test_unreachable_server_is_wrapped() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EmbeddingError, match="reach Ollama"):
        embedder_with(httpx.MockTransport(refuse)).embed_query("x")


@pytest.mark.parametrize(
    "payload",
    [{"embeddings": [[1.0]]}, {"nope": []}, {"embeddings": "bad"}],
)
def test_wrong_shape_or_count_is_rejected(payload: dict[str, object]) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))

    with pytest.raises(EmbeddingError):
        embedder_with(transport).embed_documents(["a", "b"])
