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
    score: float  # higher is better; compare only within one search


# Reciprocal rank fusion constant: how much a top rank in one list outweighs a lower one.
_RRF_K = 60


class DocumentIndex:
    """`hybrid` merges meaning-based (vector) and keyword (BM25) search; off means vector only."""

    def __init__(
        self,
        documents: DocumentStore,
        vectors: VectorStore,
        embedder: Embedder,
        *,
        hybrid: bool = True,
    ) -> None:
        self._documents = documents
        self._vectors = vectors
        self._embedder = embedder
        self._hybrid = hybrid

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
        """Return the k best chunks for the query, best first."""
        wanted = max(k * 3, 20) if self._hybrid else k
        rankings = [
            [h.chunk_id for h in self._vectors.search(self._embedder.embed_query(query), wanted)]
        ]
        if self._hybrid:
            rankings.append(self._documents.search_text(query, wanted))
        scores: dict[UUID, float] = {}
        for ranking in rankings:
            for position, chunk_id in enumerate(ranking):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (_RRF_K + position)
        best = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        chunks = {c.id: c for c in self._documents.get_chunks_by_ids(best)}
        documents: dict[UUID, Document | None] = {}
        results: list[SearchResult] = []
        for chunk_id in best:
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue  # vector outlived its chunk
            if chunk.document_id not in documents:
                documents[chunk.document_id] = self._documents.get(chunk.document_id)
            document = documents[chunk.document_id]
            if document is not None:
                results.append(SearchResult(chunk=chunk, document=document, score=scores[chunk_id]))
        return results[:k]

    def remove_document(self, document_id: UUID) -> bool:
        """Delete a document and its vectors. Returns False if it did not exist."""
        self._vectors.delete([c.id for c in self._documents.get_chunks(document_id)])
        return self._documents.delete(document_id)
