from pathlib import Path

import pytest

from local_doc_chat.ingest.errors import EncryptedPdfError, NotAPdfError
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.models import Document, DocumentStatus, ExtractedPage
from local_doc_chat.ingest.service import IngestService
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.store.documents import SqliteDocumentStore
from pdf_fixtures import encrypt_pdf, make_pdf


class CountingExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self._real = PdfplumberExtractor()

    def extract(self, data: bytes, limits: PdfLimits) -> list[ExtractedPage]:
        self.calls += 1
        return self._real.extract(data, limits)


class BlindFirstLookupStore(SqliteDocumentStore):
    """Hides the document on the first hash lookup, as if another upload lands right after it."""

    _blind = True

    def get_by_sha256(self, sha256: str) -> Document | None:
        if self._blind:
            self._blind = False
            return None
        return super().get_by_sha256(sha256)


@pytest.fixture
def store(tmp_path: Path) -> SqliteDocumentStore:
    return SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")


@pytest.fixture
def extractor() -> CountingExtractor:
    return CountingExtractor()


@pytest.fixture
def service(store: SqliteDocumentStore, extractor: CountingExtractor) -> IngestService:
    return IngestService(extractor, store, PdfLimits())


def test_ingests_new_pdf(service: IngestService, store: SqliteDocumentStore) -> None:
    pdf = make_pdf(["Hello world", "Second page"])

    result = service.ingest(pdf, "paper.pdf")

    assert result.created is True
    document = result.document
    assert (document.filename, document.page_count, document.size_bytes) == (
        "paper.pdf",
        2,
        len(pdf),
    )
    assert document.status == DocumentStatus.READY
    assert store.get(document.id) == document
    assert store.read_pdf(document.id) == pdf
    assert [p.text for p in store.get_pages(document.id)] == ["Hello world", "Second page"]
    chunks = store.get_chunks(document.id)
    assert [(c.page_number, c.text) for c in chunks] == [(1, "Hello world"), (2, "Second page")]
    assert [w.text for w in chunks[0].words] == ["Hello", "world"]


def test_same_bytes_return_existing_without_reextracting(
    service: IngestService, store: SqliteDocumentStore, extractor: CountingExtractor
) -> None:
    pdf = make_pdf(["Hello"])
    first = service.ingest(pdf, "first.pdf")

    second = service.ingest(pdf, "renamed.pdf")

    assert second.created is False
    assert second.document == first.document
    assert extractor.calls == 1
    assert len(store.list_documents()) == 1


def test_pdf_without_text_is_flagged(service: IngestService) -> None:
    result = service.ingest(make_pdf(["", ""]), "scan.pdf")

    assert result.document.status == DocumentStatus.NO_TEXT


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"not a pdf", NotAPdfError),
        (encrypt_pdf(make_pdf(["secret"]), "pw"), EncryptedPdfError),
    ],
)
def test_rejected_files_store_nothing(
    service: IngestService, store: SqliteDocumentStore, data: bytes, error: type[Exception]
) -> None:
    with pytest.raises(error):
        service.ingest(data, "bad.pdf")

    assert store.list_documents() == []


def test_lost_race_returns_the_winner(tmp_path: Path, extractor: CountingExtractor) -> None:
    store = BlindFirstLookupStore(tmp_path / "db.sqlite", tmp_path / "pdfs")
    service = IngestService(extractor, store, PdfLimits())
    pdf = make_pdf(["Hello"])
    winner = IngestService(
        extractor, SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs"), PdfLimits()
    ).ingest(pdf, "a.pdf")

    result = service.ingest(pdf, "b.pdf")

    assert result.created is False
    assert result.document.id == winner.document.id
