"""The chat model behind a small interface."""

from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError


class ModelError(Exception):
    """The chat model is unreachable, missing or returned bad data."""


class ChatModel(Protocol):
    """Swappable text-in, text-out model."""

    def complete(self, prompt: str) -> str: ...


class _Message(BaseModel):
    content: str


class _ChatResponse(BaseModel):
    message: _Message


class OllamaChatModel:
    """ChatModel backed by a local Ollama server. Temperature 0 keeps grading repeatable."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            response = self._client.post("/api/chat", json=payload)
        except httpx.HTTPError as exc:
            msg = f"Could not reach Ollama: {exc}"
            raise ModelError(msg) from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            msg = f"Model {self._model!r} not found; run `ollama pull {self._model}`"
            raise ModelError(msg)
        if response.is_error:
            msg = f"Ollama returned {response.status_code}: {response.text[:200]}"
            raise ModelError(msg)
        try:
            return _ChatResponse.model_validate_json(response.content).message.content
        except ValidationError as exc:
            msg = "Ollama returned an unreadable chat response"
            raise ModelError(msg) from exc
