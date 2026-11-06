"""FastAPI application."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Self
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from local_doc_chat.agent.graph import Answer, DocAgent
from local_doc_chat.agent.model import ChatModel, ModelError, OllamaChatModel
from local_doc_chat.ingest.errors import FileTooLargeError, InvalidPdfError
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.models import Document
from local_doc_chat.ingest.service import IngestResult, IngestService
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.store.documents import DocumentNotFoundError, SqliteDocumentStore
from local_doc_chat.store.embeddings import Embedder, EmbeddingError, OllamaEmbedder
from local_doc_chat.store.index import DocumentIndex
from local_doc_chat.store.vectors import SqliteVecStore


class Settings(BaseModel):
    data_dir: Path = Path("data")
    ollama_base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    embed_dimensions: int = Field(default=768, ge=1)  # must match embed_model's output size
    chat_model: str = "llama3.1:8b"
    limits: PdfLimits = PdfLimits()

    @classmethod
    def from_env(cls) -> Self:
        env = os.environ
        values = {
            "data_dir": env.get("DATA_DIR"),
            "ollama_base_url": env.get("OLLAMA_BASE_URL"),
            "embed_model": env.get("OLLAMA_EMBED_MODEL"),
            "embed_dimensions": env.get("EMBED_DIMENSIONS"),
            "chat_model": env.get("OLLAMA_CHAT_MODEL"),
        }
        return cls.model_validate({k: v for k, v in values.items() if v})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _error_handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    def handle(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status_code)

    return handle


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    model: ChatModel | None = None,
) -> FastAPI:
    """Build the app. Run with `uvicorn local_doc_chat.main:create_app --factory`."""
    settings = settings or Settings.from_env()
    documents = SqliteDocumentStore(
        settings.data_dir / "documents.sqlite", settings.data_dir / "pdfs"
    )
    vectors = SqliteVecStore(settings.data_dir / "vectors.sqlite", settings.embed_dimensions)
    index = DocumentIndex(
        documents,
        vectors,
        embedder or OllamaEmbedder(settings.embed_model, settings.ollama_base_url),
    )
    ingest = IngestService(PdfplumberExtractor(), documents, settings.limits)
    agent = DocAgent(index, model or OllamaChatModel(settings.chat_model, settings.ollama_base_url))

    app = FastAPI(title="Local Doc Chat")
    app.add_exception_handler(FileTooLargeError, _error_handler(413))
    app.add_exception_handler(InvalidPdfError, _error_handler(422))
    app.add_exception_handler(EmbeddingError, _error_handler(502))
    app.add_exception_handler(ModelError, _error_handler(502))

    def ingest_and_index(data: bytes, filename: str) -> IngestResult:
        try:
            result = ingest.ingest(data, filename)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid filename") from exc
        if result.created:
            try:
                index.index_document(result.document.id)
            except Exception:
                # Undo the upload so sending the file again retries cleanly.
                index.remove_document(result.document.id)
                raise
        return result

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/documents")
    def list_documents() -> list[Document]:
        return documents.list_documents()

    @app.post("/documents")
    async def upload(
        request: Request, filename: Annotated[str, Query(min_length=1, max_length=255)]
    ) -> IngestResult:
        """The PDF is the raw request body."""
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > settings.limits.max_bytes:
            raise FileTooLargeError(int(declared), settings.limits.max_bytes)
        return await run_in_threadpool(ingest_and_index, await request.body(), filename)

    @app.get("/documents/{document_id}/pdf")
    def get_pdf(document_id: UUID) -> Response:
        try:
            data = documents.read_pdf(document_id)
        except DocumentNotFoundError:
            raise HTTPException(404, "Document not found") from None
        return Response(data, media_type="application/pdf")

    @app.delete("/documents/{document_id}", status_code=204)
    def delete_document(document_id: UUID) -> Response:
        if not index.remove_document(document_id):
            raise HTTPException(404, "Document not found")
        return Response(status_code=204)

    @app.post("/ask")
    def ask(body: AskRequest) -> Answer:
        return agent.ask(body.question)

    return app
