"""Turn text into vectors."""

from collections.abc import Sequence
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError


class EmbeddingError(Exception):
    """Embedding failed: the model is unreachable, missing or returned bad data."""


class Embedder(Protocol):
    """Swappable text embedder."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class _EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class OllamaEmbedder:
    """Embedder backed by a local Ollama server.

    shortcut: no query/document prefixes, so models like nomic-embed-text run below their best;
    tune against the retrieval eval in milestone 4.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        batch_size: int = 32,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._batch_size = batch_size
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed(list(texts[start : start + self._batch_size])))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, batch: list[str]) -> list[list[float]]:
        try:
            response = self._client.post("/api/embed", json={"model": self._model, "input": batch})
        except httpx.HTTPError as exc:
            msg = f"Could not reach Ollama: {exc}"
            raise EmbeddingError(msg) from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            msg = f"Model {self._model!r} not found; run `ollama pull {self._model}`"
            raise EmbeddingError(msg)
        if response.is_error:
            msg = f"Ollama returned {response.status_code}: {response.text[:200]}"
            raise EmbeddingError(msg)
        try:
            vectors = _EmbedResponse.model_validate_json(response.content).embeddings
        except ValidationError as exc:
            msg = "Ollama returned an unreadable embedding response"
            raise EmbeddingError(msg) from exc
        if len(vectors) != len(batch):
            msg = f"Asked for {len(batch)} embeddings, got {len(vectors)}"
            raise EmbeddingError(msg)
        return vectors
