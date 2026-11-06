from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import pytest

from local_doc_chat.evaluation.pdfgen import make_pdf
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.models import Document
from local_doc_chat.ingest.service import IngestService
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.store.documents import DocumentNotFoundError, SqliteDocumentStore
from local_doc_chat.store.embeddings import EmbeddingError
from local_doc_chat.store.index import DocumentIndex
from local_doc_chat.store.vectors import SqliteVecStore

VOCAB = ["cat", "dog", "fish", "bird"]


class WordCountEmbedder:
    """Counts vocabulary words, so texts sharing words are close."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        words = text.lower().split()
        return [float(words.count(w)) for w in VOCAB]


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        msg = "down"
        raise EmbeddingError(msg)

    def embed_query(self, text: str) -> list[float]:
        msg = "down"
        raise EmbeddingError(msg)


@pytest.fixture
def documents(tmp_path: Path) -> SqliteDocumentStore:
    return SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")


@pytest.fixture
def vectors(tmp_path: Path) -> SqliteVecStore:
    return SqliteVecStore(tmp_path / "vectors.sqlite", dimensions=len(VOCAB))


@pytest.fixture
def index(documents: SqliteDocumentStore, vectors: SqliteVecStore) -> DocumentIndex:
    return DocumentIndex(documents, vectors, WordCountEmbedder())


def ingest(documents: SqliteDocumentStore, pages: list[str], name: str = "pets.pdf") -> Document:
    service = IngestService(PdfplumberExtractor(), documents, PdfLimits())
    return service.ingest(make_pdf(pages), name).document


def test_search_finds_the_matching_page_with_source(
    documents: SqliteDocumentStore, index: DocumentIndex
) -> None:
    document = ingest(documents, ["cat cat cat", "dog dog", "fish"])
    assert index.index_document(document.id) == 3

    results = index.search("dog", k=2)

    top = results[0]
    assert (top.chunk.page_number, top.chunk.text) == (2, "dog dog")
    assert top.document.filename == "pets.pdf"
    assert [w.text for w in top.chunk.words] == ["dog", "dog"]
    assert results[0].distance <= results[1].distance


def test_indexing_twice_does_not_duplicate(
    documents: SqliteDocumentStore, index: DocumentIndex
) -> None:
    document = ingest(documents, ["cat", "dog"])

    index.index_document(document.id)
    index.index_document(document.id)

    assert len(index.search("cat dog", k=10)) == 2


def test_search_spans_documents(documents: SqliteDocumentStore, index: DocumentIndex) -> None:
    pets = ingest(documents, ["cat"], "pets.pdf")
    zoo = ingest(documents, ["bird"], "zoo.pdf")
    index.index_document(pets.id)
    index.index_document(zoo.id)

    assert index.search("bird", k=1)[0].document.filename == "zoo.pdf"


def test_remove_document_removes_rows_and_vectors(
    documents: SqliteDocumentStore, index: DocumentIndex
) -> None:
    document = ingest(documents, ["cat"])
    index.index_document(document.id)

    assert index.remove_document(document.id) is True

    assert documents.get(document.id) is None
    assert index.search("cat", k=5) == []
    assert index.remove_document(document.id) is False


def test_vector_without_a_chunk_is_skipped(index: DocumentIndex, vectors: SqliteVecStore) -> None:
    vectors.add([uuid4()], [[1, 0, 0, 0]])

    assert index.search("cat", k=5) == []


def test_index_unknown_document(index: DocumentIndex) -> None:
    with pytest.raises(DocumentNotFoundError):
        index.index_document(uuid4())


def test_embedding_failure_leaves_existing_vectors(
    documents: SqliteDocumentStore, vectors: SqliteVecStore, index: DocumentIndex
) -> None:
    document = ingest(documents, ["cat"])
    index.index_document(document.id)
    broken = DocumentIndex(documents, vectors, FailingEmbedder())

    with pytest.raises(EmbeddingError):
        broken.index_document(document.id)

    assert len(index.search("cat", k=5)) == 1
