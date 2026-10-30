import pytest

from local_doc_chat.ingest.errors import (
    EmptyFileError,
    FileTooLargeError,
    InvalidPdfError,
    NotAPdfError,
)
from local_doc_chat.ingest.validation import PdfLimits, validate_pdf_bytes

LIMITS = PdfLimits(max_bytes=100)


def test_accepts_pdf_header() -> None:
    validate_pdf_bytes(b"%PDF-1.7\n...", LIMITS)


def test_rejects_empty() -> None:
    with pytest.raises(EmptyFileError):
        validate_pdf_bytes(b"", LIMITS)


def test_rejects_too_large() -> None:
    with pytest.raises(FileTooLargeError) as exc_info:
        validate_pdf_bytes(b"%PDF-" + b"0" * 100, LIMITS)

    assert exc_info.value.max_bytes == 100


@pytest.mark.parametrize("data", [b"hello world", b"PK\x03\x04zip", b" %PDF-1.7"])
def test_rejects_non_pdf(data: bytes) -> None:
    with pytest.raises(NotAPdfError):
        validate_pdf_bytes(data, LIMITS)


def test_all_rejections_share_a_base_class() -> None:
    with pytest.raises(InvalidPdfError):
        validate_pdf_bytes(b"", LIMITS)
