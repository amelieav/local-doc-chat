from uuid import uuid4

import pytest

from local_doc_chat.ingest.chunking import chunk_pages
from local_doc_chat.ingest.models import ExtractedPage, Word

DOC = uuid4()


def make_page(number: int, word_count: int) -> ExtractedPage:
    words = tuple(
        Word(text=f"p{number}w{i}", x0=i, top=number, x1=i + 1, bottom=number + 1)
        for i in range(word_count)
    )
    return ExtractedPage(
        page_number=number,
        width=612,
        height=792,
        text=" ".join(w.text for w in words),
        words=words,
    )


def test_no_words_no_chunks() -> None:
    assert chunk_pages(DOC, [make_page(1, 0)]) == []


def test_short_page_is_one_chunk_with_boxes() -> None:
    page = make_page(1, 5)

    (chunk,) = chunk_pages(DOC, [page])

    assert chunk.text == page.text
    assert chunk.words == page.words
    assert (chunk.document_id, chunk.page_number, chunk.chunk_index) == (DOC, 1, 0)


def test_long_page_splits_into_overlapping_windows() -> None:
    chunks = chunk_pages(DOC, [make_page(1, 25)], max_words=10, overlap=3)

    starts = [int(c.words[0].text.split("w")[1]) for c in chunks]
    ends = [int(c.words[-1].text.split("w")[1]) for c in chunks]
    assert starts == [0, 7, 14, 21]
    assert ends == [9, 16, 23, 24]


def test_exact_fit_has_no_tail_chunk() -> None:
    chunks = chunk_pages(DOC, [make_page(1, 10)], max_words=10, overlap=3)

    assert len(chunks) == 1


def test_chunks_never_cross_pages_and_index_runs_across_document() -> None:
    chunks = chunk_pages(DOC, [make_page(1, 12), make_page(2, 4)], max_words=10, overlap=2)

    assert [(c.chunk_index, c.page_number) for c in chunks] == [(0, 1), (1, 1), (2, 2)]
    assert all(w.text.startswith(f"p{c.page_number}") for c in chunks for w in c.words)


@pytest.mark.parametrize("overlap", [-1, 10, 11])
def test_rejects_bad_overlap(overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_pages(DOC, [], max_words=10, overlap=overlap)
