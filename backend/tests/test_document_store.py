import hashlib
from pathlib import Path

import pytest

from local_doc_chat.ingest.models import Document, DocumentStatus, Page
from local_doc_chat.store.documents import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    SqliteDocumentStore,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteDocumentStore:
    return SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")


def make_doc(pdf: bytes, filename: str = "a.pdf") -> tuple[Document, list[Page]]:
    document = Document(
        filename=filename,
        sha256=hashlib.sha256(pdf).hexdigest(),
        size_bytes=len(pdf),
        page_count=2,
        status=DocumentStatus.READY,
    )
    pages = [Page(document_id=document.id, page_number=n, text=f"page {n}") for n in (2, 1)]
    return document, pages


def test_add_then_read_back(store: SqliteDocumentStore) -> None:
    pdf = b"%PDF-one"
    document, pages = make_doc(pdf)

    store.add(document, pdf, pages)

    assert store.get(document.id) == document
    assert store.get_by_sha256(document.sha256) == document
    assert store.read_pdf(document.id) == pdf
    assert [p.page_number for p in store.get_pages(document.id)] == [1, 2]
    assert store.get_pages(document.id)[0].text == "page 1"


def test_unknown_document(store: SqliteDocumentStore) -> None:
    document, _ = make_doc(b"%PDF-x")

    assert store.get(document.id) is None
    assert store.get_by_sha256(document.sha256) is None
    assert store.get_pages(document.id) == []
    assert store.delete(document.id) is False
    with pytest.raises(DocumentNotFoundError):
        store.read_pdf(document.id)


def test_duplicate_content_is_rejected_and_original_kept(store: SqliteDocumentStore) -> None:
    pdf = b"%PDF-dup"
    first, first_pages = make_doc(pdf, "first.pdf")
    second, second_pages = make_doc(pdf, "second.pdf")
    store.add(first, pdf, first_pages)

    with pytest.raises(DuplicateDocumentError):
        store.add(second, pdf, second_pages)

    assert store.list_documents() == [first]
    assert store.get_pages(second.id) == []
    assert store.read_pdf(first.id) == pdf


def test_list_documents_oldest_first(store: SqliteDocumentStore) -> None:
    added = []
    for i in range(3):
        pdf = f"%PDF-{i}".encode()
        document, pages = make_doc(pdf, f"{i}.pdf")
        store.add(document, pdf, pages)
        added.append(document.id)

    assert [d.id for d in store.list_documents()] == added


def test_delete_removes_rows_and_file(store: SqliteDocumentStore, tmp_path: Path) -> None:
    pdf = b"%PDF-del"
    document, pages = make_doc(pdf)
    store.add(document, pdf, pages)

    assert store.delete(document.id) is True

    assert store.get(document.id) is None
    assert store.get_pages(document.id) == []
    assert not (tmp_path / "pdfs" / f"{document.sha256}.pdf").exists()


def test_data_survives_reopening(store: SqliteDocumentStore, tmp_path: Path) -> None:
    pdf = b"%PDF-persist"
    document, pages = make_doc(pdf)
    store.add(document, pdf, pages)

    reopened = SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")

    assert reopened.get(document.id) == document
    assert reopened.read_pdf(document.id) == pdf
