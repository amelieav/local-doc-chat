"""Document storage: PDFs on disk, metadata and page text in SQLite."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Protocol
from uuid import UUID

from local_doc_chat.ingest.models import Document, Page


class DuplicateDocumentError(Exception):
    """A document with the same content hash is already stored."""

    def __init__(self, sha256: str) -> None:
        super().__init__(f"Document with sha256 {sha256} already exists")
        self.sha256 = sha256


class DocumentNotFoundError(Exception):
    """No document has the requested id."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Document {document_id} not found")
        self.document_id = document_id


class DocumentStore(Protocol):
    """Where uploaded documents live. Swappable behind this interface."""

    def add(self, document: Document, pdf: bytes, pages: Sequence[Page]) -> None: ...

    def get(self, document_id: UUID) -> Document | None: ...

    def get_by_sha256(self, sha256: str) -> Document | None: ...

    def list_documents(self) -> list[Document]: ...

    def get_pages(self, document_id: UUID) -> list[Page]: ...

    def read_pdf(self, document_id: UUID) -> bytes: ...

    def delete(self, document_id: UUID) -> bool: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);
"""


class SqliteDocumentStore:
    """DocumentStore keeping PDFs as `<pdf_dir>/<sha256>.pdf` and the rest in SQLite."""

    def __init__(self, db_path: Path, pdf_dir: Path) -> None:
        self._db_path = db_path
        self._pdf_dir = pdf_dir
        db_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def add(self, document: Document, pdf: bytes, pages: Sequence[Page]) -> None:
        # The insert runs first so a duplicate fails before the shared PDF file is touched.
        # A failed file write rolls the rows back.
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(document.id),
                        document.filename,
                        document.sha256,
                        document.size_bytes,
                        document.page_count,
                        document.status.value,
                        document.created_at.isoformat(),
                    ),
                )
                conn.executemany(
                    "INSERT INTO pages VALUES (?, ?, ?)",
                    [(str(p.document_id), p.page_number, p.text) for p in pages],
                )
                self._write_pdf(document.sha256, pdf)
        except sqlite3.IntegrityError as exc:
            if self.get_by_sha256(document.sha256) is not None:
                raise DuplicateDocumentError(document.sha256) from exc
            raise

    def get(self, document_id: UUID) -> Document | None:
        return self._one("SELECT * FROM documents WHERE id = ?", str(document_id))

    def get_by_sha256(self, sha256: str) -> Document | None:
        return self._one("SELECT * FROM documents WHERE sha256 = ?", sha256)

    def list_documents(self) -> list[Document]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at, id").fetchall()
        return [Document.model_validate(dict(row)) for row in rows]

    def get_pages(self, document_id: UUID) -> list[Page]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM pages WHERE document_id = ? ORDER BY page_number",
                (str(document_id),),
            ).fetchall()
        return [Page.model_validate(dict(row)) for row in rows]

    def read_pdf(self, document_id: UUID) -> bytes:
        document = self.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return self._pdf_path(document.sha256).read_bytes()

    def delete(self, document_id: UUID) -> bool:
        document = self.get(document_id)
        if document is None:
            return False
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (str(document_id),))
        self._pdf_path(document.sha256).unlink(missing_ok=True)
        return True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _one(self, query: str, param: str) -> Document | None:
        with closing(self._connect()) as conn:
            row = conn.execute(query, (param,)).fetchone()
        return None if row is None else Document.model_validate(dict(row))

    def _pdf_path(self, sha256: str) -> Path:
        return self._pdf_dir / f"{sha256}.pdf"

    def _write_pdf(self, sha256: str, pdf: bytes) -> None:
        # Write to a temp name then rename, so a crash never leaves a half-written PDF.
        target = self._pdf_path(sha256)
        temp = target.with_suffix(".tmp")
        temp.write_bytes(pdf)
        temp.replace(target)
