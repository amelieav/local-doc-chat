"""Reasons an uploaded file can be rejected."""


class IngestError(Exception):
    """Base class for all ingestion failures."""


class InvalidPdfError(IngestError):
    """The upload is not an acceptable PDF."""


class EmptyFileError(InvalidPdfError):
    """The file has no bytes."""


class FileTooLargeError(InvalidPdfError):
    """The file is bigger than the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"File is {size_bytes} bytes; the limit is {max_bytes} bytes")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class CorruptPdfError(InvalidPdfError):
    """The file has a PDF header but cannot be parsed."""

    def __init__(self) -> None:
        super().__init__("PDF is corrupt or unreadable")


class EncryptedPdfError(InvalidPdfError):
    """The PDF needs a password."""

    def __init__(self) -> None:
        super().__init__("PDF is password protected")


class NoPagesError(InvalidPdfError):
    """The PDF has zero pages."""

    def __init__(self) -> None:
        super().__init__("PDF has no pages")


class TooManyPagesError(InvalidPdfError):
    """The PDF has more pages than the configured limit."""

    def __init__(self, page_count: int, max_pages: int) -> None:
        super().__init__(f"PDF has {page_count} pages; the limit is {max_pages}")
        self.page_count = page_count
        self.max_pages = max_pages


class NotAPdfError(InvalidPdfError):
    """The file does not start with the PDF header."""

    def __init__(self) -> None:
        super().__init__("File is not a PDF")
