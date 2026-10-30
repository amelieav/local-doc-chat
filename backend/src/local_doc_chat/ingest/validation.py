"""Cheap checks on raw upload bytes, run before any PDF parsing."""

from pydantic import BaseModel, ConfigDict, Field

from local_doc_chat.ingest.errors import EmptyFileError, FileTooLargeError, NotAPdfError

PDF_HEADER = b"%PDF-"


class PdfLimits(BaseModel):
    """Upload limits. Page count is enforced after parsing."""

    model_config = ConfigDict(frozen=True)

    max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_pages: int = Field(default=500, gt=0)


def validate_pdf_bytes(data: bytes, limits: PdfLimits) -> None:
    """Raise an InvalidPdfError subclass if the bytes cannot be a PDF we accept."""
    if not data:
        raise EmptyFileError("File is empty")
    if len(data) > limits.max_bytes:
        raise FileTooLargeError(len(data), limits.max_bytes)
    if not data.startswith(PDF_HEADER):
        raise NotAPdfError
