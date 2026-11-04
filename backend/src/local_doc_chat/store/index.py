"""Ties documents, embeddings and vectors together: index chunks, search, remove."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from local_doc_chat.ingest.models import Chunk, Document
from local_doc_chat.store.documents import DocumentNotFoundError, DocumentStore
from local_doc_chat.store.embeddings import Embedder
from local_doc_chat.store.vectors import VectorStore


class SearchResult(BaseModel):
    """A chunk that matched a question, with the document it came from."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    document: Document
    distance: float


class DocumentIndex:
    def __init__(self, documents: DocumentStore, vectors: VectorStore, embedder: Embedder) -> None:
        self._documents = documents
        self._vectors = vectors
        self._embedder = embedder

    def index_document(self, document_id: UUID) -> int:
        """Embed a document's chunks. Safe to repeat. Returns the number of chunks indexed."""
        if self._documents.get(document_id) is None:
            raise DocumentNotFoundError(document_id)
        chunks = self._documents.get_chunks(document_id)
        if not chunks:
            return 0
        # Embed first so a failure leaves any existing vectors alone.
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        ids = [c.id for c in chunks]
        self._vectors.delete(ids)
        self._vectors.add(ids, vectors)
        return len(chunks)

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Return the k chunks closest to the query, nearest first."""
        hits = self._vectors.search(self._embedder.embed_query(query), k)
        chunks = {c.id: c for c in self._documents.get_chunks_by_ids([h.chunk_id for h in hits])}
        documents: dict[UUID, Document | None] = {}
        results: list[SearchResult] = []
        for hit in hits:
            chunk = chunks.get(hit.chunk_id)
            if chunk is None:
                continue  # vector outlived its chunk
            if chunk.document_id not in documents:
                documents[chunk.document_id] = self._documents.get(chunk.document_id)
            document = documents[chunk.document_id]
            if document is not None:
                results.append(SearchResult(chunk=chunk, document=document, distance=hit.distance))
        return results

    def remove_document(self, document_id: UUID) -> bool:
        """Delete a document and its vectors. Returns False if it did not exist."""
        self._vectors.delete([c.id for c in self._documents.get_chunks(document_id)])
        return self._documents.delete(document_id)
