import pytest

from local_doc_chat.ingest.errors import (
    CorruptPdfError,
    EncryptedPdfError,
    TooManyPagesError,
)
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.validation import PdfLimits
from pdf_fixtures import encrypt_pdf, make_pdf

LIMITS = PdfLimits()
extractor = PdfplumberExtractor()


def test_extracts_text_and_word_boxes_per_page() -> None:
    pages = extractor.extract(make_pdf(["Hello world", "Second page"]), LIMITS)

    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].text == "Hello world"
    assert pages[1].text == "Second page"
    assert (pages[0].width, pages[0].height) == (612, 792)
    hello, world = pages[0].words
    assert (hello.text, world.text) == ("Hello", "world")
    assert hello.x0 < hello.x1 <= world.x0 < world.x1
    assert hello.top < hello.bottom


def test_blank_page_has_empty_text() -> None:
    (page,) = extractor.extract(make_pdf([""]), LIMITS)

    assert page.text == ""
    assert page.words == ()


def test_rejects_too_many_pages() -> None:
    with pytest.raises(TooManyPagesError) as exc_info:
        extractor.extract(make_pdf(["a", "b", "c"]), PdfLimits(max_pages=2))

    assert exc_info.value.page_count == 3


def test_rejects_corrupt_pdf() -> None:
    with pytest.raises(CorruptPdfError):
        extractor.extract(b"%PDF-1.4\nthis is not really a pdf", LIMITS)


def test_rejects_encrypted_pdf() -> None:
    with pytest.raises(EncryptedPdfError):
        extractor.extract(encrypt_pdf(make_pdf(["secret"]), "pw"), LIMITS)
