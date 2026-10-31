"""Upload intake: validate, extract and store a PDF."""

import hashlib

from pydantic import BaseModel, ConfigDict

from local_doc_chat.ingest.extraction import PdfExtractor
from local_doc_chat.ingest.models import Document, DocumentStatus, Page
from local_doc_chat.ingest.validation import PdfLimits, validate_pdf_bytes
from local_doc_chat.store.documents import DocumentStore, DuplicateDocumentError


class IngestResult(BaseModel):
    """The stored document, and whether this upload created it."""

    model_config = ConfigDict(frozen=True)

    document: Document
    created: bool


class IngestService:
    def __init__(self, extractor: PdfExtractor, store: DocumentStore, limits: PdfLimits) -> None:
        self._extractor = extractor
        self._store = store
        self._limits = limits

    def ingest(self, data: bytes, filename: str) -> IngestResult:
        """Store the PDF, or return the existing document if identical bytes were uploaded before.

        Raises InvalidPdfError subclasses for files we reject.
        """
        validate_pdf_bytes(data, self._limits)
        sha256 = hashlib.sha256(data).hexdigest()
        existing = self._store.get_by_sha256(sha256)
        if existing is not None:
            return IngestResult(document=existing, created=False)

        extracted = self._extractor.extract(data, self._limits)
        document = Document(
            filename=filename,
            sha256=sha256,
            size_bytes=len(data),
            page_count=len(extracted),
            status=(
                DocumentStatus.READY
                if any(p.text.strip() for p in extracted)
                else DocumentStatus.NO_TEXT
            ),
        )
        pages = [
            Page(document_id=document.id, page_number=p.page_number, text=p.text) for p in extracted
        ]
        try:
            self._store.add(document, data, pages)
        except DuplicateDocumentError:
            # Another upload of the same file won the race after our check.
            winner = self._store.get_by_sha256(sha256)
            if winner is None:
                raise
            return IngestResult(document=winner, created=False)
        return IngestResult(document=document, created=True)
