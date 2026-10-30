"""Read text and word positions out of PDF bytes."""

from io import BytesIO
from typing import Protocol

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from local_doc_chat.ingest.errors import (
    CorruptPdfError,
    EncryptedPdfError,
    NoPagesError,
    TooManyPagesError,
)
from local_doc_chat.ingest.models import ExtractedPage, Word
from local_doc_chat.ingest.validation import PdfLimits


class PdfExtractor(Protocol):
    """Turns validated PDF bytes into per-page text. Raises InvalidPdfError subclasses."""

    def extract(self, data: bytes, limits: PdfLimits) -> list[ExtractedPage]: ...


class PdfplumberExtractor:
    """PdfExtractor backed by pdfplumber."""

    def extract(self, data: bytes, limits: PdfLimits) -> list[ExtractedPage]:
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                if not pdf.pages:
                    raise NoPagesError
                if len(pdf.pages) > limits.max_pages:
                    raise TooManyPagesError(len(pdf.pages), limits.max_pages)
                return [
                    ExtractedPage(
                        page_number=number,
                        width=float(page.width),
                        height=float(page.height),
                        text=page.extract_text() or "",
                        words=tuple(
                            Word(
                                text=w["text"],
                                x0=w["x0"],
                                top=w["top"],
                                x1=w["x1"],
                                bottom=w["bottom"],
                            )
                            for w in page.extract_words()
                        ),
                    )
                    for number, page in enumerate(pdf.pages, start=1)
                ]
        except (NoPagesError, TooManyPagesError):
            raise
        except PdfminerException as exc:
            # pdfplumber wraps the original pdfminer error as the first arg.
            if exc.args and isinstance(exc.args[0], PDFPasswordIncorrect):
                raise EncryptedPdfError from exc
            raise CorruptPdfError from exc
        except Exception as exc:
            # pdfminer raises many unrelated types on malformed input, so treat any as corrupt.
            raise CorruptPdfError from exc
