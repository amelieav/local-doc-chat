from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from fakes import HashingEmbedder, ScriptedModel
from local_doc_chat.evaluation.pdfgen import make_pdf
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.main import Settings, create_app
from local_doc_chat.store.embeddings import Embedder, EmbeddingError

PETS = make_pdf(["cats purr and sleep all day", "dogs bark and chase balls"])


def model_reply(prompt: str) -> str:
    if "Does this passage help" in prompt:
        return "yes" if "dogs bark" in prompt else "no"
    return "Dogs bark and chase balls [1]."


class BrokenEmbedder(HashingEmbedder):
    def embed_documents(self, texts: object) -> list[list[float]]:
        msg = "ollama is down"
        raise EmbeddingError(msg)


def make_client(
    tmp_path: Path, limits: PdfLimits | None = None, embedder: Embedder | None = None
) -> TestClient:
    settings = Settings(data_dir=tmp_path, embed_dimensions=64, limits=limits or PdfLimits())
    app = create_app(
        settings, embedder=embedder or HashingEmbedder(), model=ScriptedModel(model_reply)
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make_client(tmp_path)


def upload(client: TestClient, data: bytes = PETS, name: str = "pets.pdf") -> Any:  # noqa: ANN401
    # Any: the test client's response class differs across Starlette versions (httpx vs httpx2).
    return client.post(
        "/documents",
        params={"filename": name},
        content=data,
        headers={"content-type": "application/pdf"},
    )


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_list_ask_delete(client: TestClient) -> None:
    uploaded = upload(client)
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["created"] is True
    document_id = body["document"]["id"]

    listed = client.get("/documents").json()
    assert [(d["id"], d["filename"], d["page_count"]) for d in listed] == [
        (document_id, "pets.pdf", 2)
    ]

    answer = client.post("/ask", json={"question": "what do dogs do"}).json()
    assert answer["text"] == "Dogs bark and chase balls [1]."
    (citation,) = answer["citations"]
    assert (citation["filename"], citation["page_number"]) == ("pets.pdf", 2)

    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert client.get("/documents").json() == []
    after = client.post("/ask", json={"question": "what do dogs do"}).json()
    assert after["citations"] == []


def test_same_file_again_returns_existing(client: TestClient) -> None:
    first = upload(client).json()
    second = upload(client, name="renamed.pdf").json()

    assert second["created"] is False
    assert second["document"]["id"] == first["document"]["id"]
    assert len(client.get("/documents").json()) == 1


def test_rejects_non_pdf(client: TestClient) -> None:
    response = upload(client, b"just some text")

    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]


def test_rejects_oversized_upload_by_content_length(tmp_path: Path) -> None:
    client = make_client(tmp_path, limits=PdfLimits(max_bytes=10))

    response = upload(client)

    assert response.status_code == 413


def test_rejects_bad_filename(client: TestClient) -> None:
    assert upload(client, name="..").status_code == 422


def test_failed_embedding_rolls_the_upload_back(tmp_path: Path) -> None:
    client = make_client(tmp_path, embedder=BrokenEmbedder())

    response = upload(client)

    assert response.status_code == 502
    assert "ollama is down" in response.json()["detail"]
    assert client.get("/documents").json() == []


def test_delete_unknown_document(client: TestClient) -> None:
    assert client.delete(f"/documents/{uuid4()}").status_code == 404


def test_empty_question_is_rejected(client: TestClient) -> None:
    assert client.post("/ask", json={"question": ""}).status_code == 422
