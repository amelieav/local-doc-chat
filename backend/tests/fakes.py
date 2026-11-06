"""Offline stand-ins for the embedder and chat model."""

import hashlib
import re
from collections.abc import Callable, Sequence


class HashingEmbedder:
    """Bag-of-words vectors, so texts sharing words are close. Never returns a zero vector."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.01] * 64
        for word in re.findall(r"[a-z]+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1
        return vector


class ScriptedModel:
    """Chat model whose replies come from a function of the prompt. Records every prompt."""

    def __init__(self, reply: Callable[[str], str]) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply(prompt)

    def count(self, marker: str) -> int:
        return sum(marker in p for p in self.prompts)
