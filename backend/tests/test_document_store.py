import hashlib
import sqlite3
from pathlib import Path

import pytest

from local_doc_chat.ingest.models import Chunk, Document, DocumentStatus, Page, Word
from local_doc_chat.store.documents import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    SqliteDocumentStore,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteDocumentStore:
    return SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")


def make_doc(pdf: bytes, filename: str = "a.pdf") -> tuple[Document, list[Page], list[Chunk]]:
    document = Document(
        filename=filename,
        sha256=hashlib.sha256(pdf).hexdigest(),
        size_bytes=len(pdf),
        page_count=2,
        status=DocumentStatus.READY,
    )
    pages = [Page(document_id=document.id, page_number=n, text=f"page {n}") for n in (2, 1)]
    chunks = [
        Chunk(
            document_id=document.id,
            chunk_index=i,
            page_number=2 - i,
            text="page words",
            words=(Word(text="page", x0=1, top=2, x1=3, bottom=4),),
        )
        for i in (1, 0)
    ]
    return document, pages, chunks


def test_add_then_read_back(store: SqliteDocumentStore) -> None:
    pdf = b"%PDF-one"
    document, pages, chunks = make_doc(pdf)

    store.add(document, pdf, pages, chunks)

    assert store.get(document.id) == document
    assert store.get_by_sha256(document.sha256) == document
    assert store.read_pdf(document.id) == pdf
    assert [p.page_number for p in store.get_pages(document.id)] == [1, 2]
    assert store.get_pages(document.id)[0].text == "page 1"
    assert store.get_chunks(document.id) == sorted(chunks, key=lambda c: c.chunk_index)


def test_unknown_document(store: SqliteDocumentStore) -> None:
    document, _, _ = make_doc(b"%PDF-x")

    assert store.get(document.id) is None
    assert store.get_by_sha256(document.sha256) is None
    assert store.get_pages(document.id) == []
    assert store.get_chunks(document.id) == []
    assert store.delete(document.id) is False
    with pytest.raises(DocumentNotFoundError):
        store.read_pdf(document.id)


def test_duplicate_content_is_rejected_and_original_kept(store: SqliteDocumentStore) -> None:
    pdf = b"%PDF-dup"
    first, first_pages, first_chunks = make_doc(pdf, "first.pdf")
    second, second_pages, second_chunks = make_doc(pdf, "second.pdf")
    store.add(first, pdf, first_pages, first_chunks)

    with pytest.raises(DuplicateDocumentError):
        store.add(second, pdf, second_pages, second_chunks)

    assert store.list_documents() == [first]
    assert store.get_pages(second.id) == []
    assert store.get_chunks(second.id) == []
    assert store.read_pdf(first.id) == pdf


def test_list_documents_oldest_first(store: SqliteDocumentStore) -> None:
    added = []
    for i in range(3):
        pdf = f"%PDF-{i}".encode()
        document, pages, chunks = make_doc(pdf, f"{i}.pdf")
        store.add(document, pdf, pages, chunks)
        added.append(document.id)

    assert [d.id for d in store.list_documents()] == added


def test_delete_removes_rows_and_file(store: SqliteDocumentStore, tmp_path: Path) -> None:
    pdf = b"%PDF-del"
    document, pages, chunks = make_doc(pdf)
    store.add(document, pdf, pages, chunks)

    assert store.delete(document.id) is True

    assert store.get(document.id) is None
    assert store.get_pages(document.id) == []
    assert store.get_chunks(document.id) == []
    assert not (tmp_path / "pdfs" / f"{document.sha256}.pdf").exists()


def test_data_survives_reopening(store: SqliteDocumentStore, tmp_path: Path) -> None:
    pdf = b"%PDF-persist"
    document, pages, chunks = make_doc(pdf)
    store.add(document, pdf, pages, chunks)

    reopened = SqliteDocumentStore(tmp_path / "db.sqlite", tmp_path / "pdfs")

    assert reopened.get(document.id) == document
    assert reopened.read_pdf(document.id) == pdf
    assert len(reopened.get_chunks(document.id)) == 2


def add_text_doc(store: SqliteDocumentStore, texts: list[str], name: str = "t.pdf") -> list[Chunk]:
    pdf = name.encode() + b"".join(t.encode() for t in texts)
    document, pages, _ = make_doc(pdf, name)
    chunks = [
        Chunk(
            document_id=document.id,
            chunk_index=i,
            page_number=1,
            text=t,
            words=(Word(text="x", x0=1, top=2, x1=3, bottom=4),),
        )
        for i, t in enumerate(texts)
    ]
    store.add(document, pdf, pages, chunks)
    return chunks


def test_search_text_matches_words_and_stems(store: SqliteDocumentStore) -> None:
    chunks = add_text_doc(store, ["China built many solar plants", "Rain fell on the farms"])

    assert store.search_text("Who builds solar?", 5) == [chunks[0].id]
    assert store.search_text("the of and", 5) == []  # only stop words
    assert store.search_text("zebra", 5) == []


def test_search_text_forgets_deleted_documents(store: SqliteDocumentStore) -> None:
    chunks = add_text_doc(store, ["unique marmot sentence"])
    assert store.search_text("marmot", 5) == [chunks[0].id]

    store.delete(chunks[0].document_id)

    assert store.search_text("marmot", 5) == []


def test_keyword_index_is_built_for_an_older_database(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL
            UNIQUE, size_bytes INTEGER NOT NULL, page_count INTEGER NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE pages (document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL, text TEXT NOT NULL,
            PRIMARY KEY (document_id, page_number));
        CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES
            documents(id) ON DELETE CASCADE, chunk_index INTEGER NOT NULL, page_number INTEGER NOT
            NULL, text TEXT NOT NULL, words TEXT NOT NULL, UNIQUE (document_id, chunk_index));
        INSERT INTO documents VALUES ('d', 'old.pdf', 'x', 1, 1, 'ready', '2026-01-01T00:00:00');
        INSERT INTO chunks VALUES ('00000000-0000-0000-0000-000000000001', 'd', 0, 1,
            'an old walrus chunk', '[]');
        """
    )
    conn.commit()
    conn.close()

    store = SqliteDocumentStore(db, tmp_path / "pdfs")

    assert [str(i) for i in store.search_text("walrus", 5)] == [
        "00000000-0000-0000-0000-000000000001"
    ]
